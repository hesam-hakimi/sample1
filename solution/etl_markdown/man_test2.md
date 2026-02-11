We need to refactor the NL→SQL POC:
- Metadata source is Azure AI Search (Cognitive Search), NOT SQL meta tables.
- The metadata file is pipe-separated (|) with a header row (like a PSV).
- We still must execute the final generated SQL against Azure SQL Database (pyodbc MSI).
- UI is chat-only (Gradio Chatbot with messages format).
- Must be safe: read-only SQL only, confirmation before running dbo.* queries.
- Must work without CREATE TABLE permission in SQL.
- Must work even if we do not have permission to CREATE INDEX in Azure AI Search (handle gracefully).

========================================================
A) CONFIG
========================================================
Update app/config.py + .env.example with these new variables:

AI_SEARCH_ENDPOINT=            # e.g. https://<search>.search.windows.net
AI_SEARCH_INDEX=metadata-psv   # index name
AI_SEARCH_USE_MSI=true
AI_SEARCH_TOP_K=8             # how many metadata docs to retrieve per question
AI_SEARCH_SEMANTIC=false      # optional future

Keep existing:
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_API_VERSION
AZURE_OPENAI_DEPLOYMENT
SQL_SERVER
SQL_DATABASE
SQL_DRIVER

Config must validate required vars and raise clear error messages.

========================================================
B) DEFINE A METADATA STORE INTERFACE
========================================================
Create app/metadata_store.py

- Create Protocol/ABC:
  class MetadataStore:
    def retrieve(self, query: str, top_k: int) -> list[dict]:
        """Returns normalized metadata docs (dicts) with standard keys."""
    def health(self) -> tuple[bool, str]:
        """Checks that index exists and is reachable."""

- Create implementation:
  class AzureAISearchMetadataStore(MetadataStore):
    - Uses azure-search-documents SDK with ManagedIdentityCredential.
    - Uses SearchClient for querying.
    - retrieve() should:
        - call search() with query text
        - select only useful fields
        - return list of normalized dicts

Normalized doc keys must include:
  schema_name, table_name, column_name, data_type,
  business_name, business_description,
  steward, zone_name,
  pii, pci, security_classification_candidate,
  data_treatment, last_modified,
  source_id (key)

If any field missing, set to "".

========================================================
C) CREATE AI SEARCH INDEX + INGESTION (PIPE SEPARATED FILE)
========================================================
Add new dependency in requirements.txt:
- azure-search-documents
- azure-core

Create scripts/ai_search_setup.py:
- Purpose: create the search index (only if user has permission)
- Must not run automatically at app startup.

Index requirements (Phase 1: keyword search only):
- Key field: id (string, key=True) -> make stable id like f"{schema}.{table}.{column}" + hash or GUID
- SearchableFields:
    schema_name, table_name, column_name,
    business_name, business_description,
    steward, edc_model_name, zone_name
- Filterable fields:
    schema_name, table_name, pii, pci, security_classification_candidate, data_treatment
- Sortable:
    last_modified (optional)
- Use SearchIndexClient and SearchIndex models:
  from azure.search.documents.indexes import SearchIndexClient
  from azure.search.documents.indexes.models import SearchIndex, SimpleField, SearchableField

Graceful behavior:
- If create_index fails due to RBAC, print a clear message:
  "No permission to create index. Ask admin or use an existing index name."

Create scripts/ai_search_ingest_psv.py:
- Inputs (CLI args):
    --file <path_to_pipe_separated_file>
    --endpoint <AI_SEARCH_ENDPOINT or env>
    --index <AI_SEARCH_INDEX or env>
- Read using csv.DictReader with delimiter='|'
- Clean values: strip whitespace, replace \t sequences, normalize empty to ""
- Create documents with the normalized keys above + id
- Upload documents using SearchClient.upload_documents in batches (e.g., 500)
- Print counts and success/failure
- Must not require keys: use ManagedIdentityCredential
- If upload fails due to auth, show actionable message

Also create a tiny sample file for tests:
- tests/data/sample_metadata.psv (few rows) with the same headers.

========================================================
D) UPDATE NL2SQL PIPELINE (RETRIEVAL FROM AI SEARCH)
========================================================
Update app/nl2sql.py to remove dependency on SQL meta.* entirely.

New runtime flow per user question:
1) If greeting/smalltalk -> respond directly (no DB, no search)
2) Else retrieve metadata docs:
   docs = metadata_store.retrieve(user_text, top_k=config.AI_SEARCH_TOP_K)

3) Build a compact metadata context string for LLM:
   - Include a table-centric view:
     - list unique tables discovered, top columns per table
   - Include business definitions:
     - business_name + business_description
   - Include governance flags:
     - pii, pci, classification, treatment
   - Limit token size:
     - max 8 docs, truncate descriptions, avoid huge dumps
   - Also include a compact JSON sample of docs (max 8)

4) Call LLM to generate SQL:
   - Provide system prompt rules:
     - Use ONLY tables/columns present in retrieved metadata docs
     - If metadata is insufficient, ask clarifying question instead of guessing
     - SQL Server dialect
     - Output STRICT JSON:
       {"sql": "...", "explanation": "...", "assumptions": [...], "needs_confirmation": [...]}
   - Parse JSON robustly using existing extract_json()

5) Validate SQL:
   - validate_business_sql(sql) read-only SELECT/CTE only
   - Require confirmation for dbo.* queries (YES/NO)
   - Enforce row limit via TOP if missing OR enforce in db.execute_query(max_rows=...) (already exists)

6) If user confirms:
   - execute SQL against Azure SQL via app/db.py
   - format results inline in chat:
     - markdown table (max 20 rows)
     - short summary (row count, columns)
     - compact JSON sample (max 50 rows)
   - Append a TOOL_RESULT message to conversation state containing:
     - executed sql
     - markdown table + summary + compact json
   - Then call LLM again to generate a human-friendly explanation USING the tool result
     (so LLM has access to the data)

Error behavior:
- If AI Search is unreachable or index missing:
  - show friendly message: "Metadata search is not available. Ask admin to provision index or verify endpoint/index."
  - Do not crash
- If metadata retrieval returns 0 docs:
  - assistant asks clarifying question:
    “I couldn’t find matching tables/columns. Which schema/table should I use?” etc.

========================================================
E) CHAT-ONLY UI: SHOW RESULTS IN CHAT, AND LLM CAN SEE THEM
========================================================
Update app/ui.py:
- gr.Chatbot(type="messages")
- Textbox + Send + optional “List Tables” button
- The chatbot value MUST always be list[{"role","content"}]

When showing data in chat:
- tool messages must be converted to assistant-visible content:
  Prefix with "**[DATA]**" and then show:
    SQL code block
    markdown table
    summary

List Tables behavior:
- Since metadata is in AI Search, “List Tables” should:
  - Query AI Search to get distinct schema/table values.
  - Use faceting if available:
     search_client.search(search_text="*", facets=["schema_name,count:1000","table_name,count:1000"], top=0)
    If facet not supported or returns empty, fallback:
     retrieve("*", top_k=200) and compute unique pairs in python
  - Show results in chat (markdown list)

Important: This “List Tables” must not query SQL system tables because our metadata source is search.

========================================================
F) UPDATE/ADD NEW MODULES
========================================================
Add:
- app/ai_search_client.py (optional helper)
- app/metadata_store.py (required)
- scripts/ai_search_setup.py (required)
- scripts/ai_search_ingest_psv.py (required)
- tests for search retrieval and ingestion parsing

Keep existing:
- app/db.py for SQL execution
- app/sql_safety.py for SQL validation
- app/llm_client.py for Azure OpenAI
- app/formatting.py for df formatting (if exists)

========================================================
G) TESTS (NO REAL AZURE)
========================================================
All tests must mock Azure clients.

1) tests/test_ingest_psv.py
- Test the PSV parser reads delimiter '|'
- Test cleaning (strip, tabs)
- Test id generation stable

2) tests/test_metadata_store.py
- Mock SearchClient.search return iterator of dict-like results
- Ensure retrieve() returns normalized docs

3) tests/test_nl2sql_retrieval_flow.py
- Mock metadata_store.retrieve() to return sample docs
- Mock LLMClient.chat to return valid JSON SQL
- Ensure SQL validation happens
- Ensure if docs empty -> assistant asks clarifying question and does not generate SQL

4) tests/test_ui_message_format.py
- Ensure ui handlers return list of dicts {"role","content"}

Acceptance criteria:
- App no longer queries meta.* SQL tables.
- Metadata retrieval is from Azure AI Search only.
- Ingestion scripts can load pipe-separated file into the search index.
- SQL still runs against Azure SQL and results show inline in chat.
- LLM can see query results via TOOL_RESULT messages and can summarize them in follow-up.
- pytest -q passes.
- Provide full updated contents for all modified/new files.
