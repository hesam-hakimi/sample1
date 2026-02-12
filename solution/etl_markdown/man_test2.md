Implement a new feature in the Gradio UI:

FEATURE GOAL
1) Add a new UI tab called "Azure AI Search".
   In that tab the client can:
   - List available indexes from the Azure AI Search endpoint
   - Select an existing index OR create a new index (if permitted)
   - Upload a pipe-separated metadata file (| delimited) and ingest it into the selected index
   - Refresh indexes list after create/upload
   - See clear, user-friendly status messages (no stack traces)

2) In the Chat tab:
   - Add a dropdown of available indexes
   - The selected index becomes the metadata reference for the NL→SQL flow
   - Changing the index should immediately affect subsequent chat turns

CONSTRAINTS
- Do NOT use Runner or Agents.
- Authentication:
  - Prefer Managed Identity (MSI) but handle multi-identity scenario by supporting explicit client_id.
  - Must also support local dev fallback (AzureCliCredential).
- Must not require SQL CREATE TABLE permission (metadata is NOT stored in SQL).
- Still execute generated SQL against Azure SQL (pyodbc MSI) after user confirmation.
- Must keep Gradio Chatbot type="messages" format: list[{"role","content"}].

========================================================
A) CONFIG + IDENTITY (robust)
========================================================
1) Ensure .env is loaded (python-dotenv). Config loads env reliably.
2) Add/confirm these env vars (app/config.py + .env.example):
   AI_SEARCH_ENDPOINT=
   AI_SEARCH_USE_MSI=true
   AI_SEARCH_MANAGED_IDENTITY_CLIENT_ID=   # optional
   AI_SEARCH_DEFAULT_INDEX=                # optional
   AI_SEARCH_TOP_K=8

3) Add app/identity.py:
   - def get_search_credential(config) -> TokenCredential
     If config.AI_SEARCH_USE_MSI:
        client_id = config.AI_SEARCH_MANAGED_IDENTITY_CLIENT_ID or os.getenv("AZURE_CLIENT_ID")
        return ManagedIdentityCredential(client_id=client_id) if client_id else ManagedIdentityCredential()
     Else:
        return AzureCliCredential()

   - Provide clear exception text for:
     "Multiple user assigned identities exist" => tell user to set AI_SEARCH_MANAGED_IDENTITY_CLIENT_ID or AZURE_CLIENT_ID.
     IMDS not available => tell user to use AI_SEARCH_USE_MSI=false for local dev.

========================================================
B) Azure AI Search service layer (single place for index ops)
========================================================
Create app/ai_search_service.py:

class AISearchService:
  def __init__(self, endpoint: str, credential: TokenCredential):
     - store SearchIndexClient + ability to create SearchClient per index

  def list_indexes(self) -> list[str]:
     - uses SearchIndexClient.list_indexes()
     - returns sorted names

  def create_metadata_index(self, index_name: str) -> tuple[bool,str]:
     - creates index schema for our metadata documents
     - use SearchIndexClient.create_index(SearchIndex(...))
     - If forbidden/unauthorized -> return (False, friendly message)
     - If already exists -> return (True, "Index already exists")

  def ingest_pipe_file(self, index_name: str, file_path: str) -> tuple[int,int,str]:
     - Reads pipe-separated file using csv.DictReader(delimiter="|")
     - Normalizes field names (strip BOM, trim spaces)
     - Normalizes values: strip whitespace, replace tabs, convert None to ""
     - Generate stable id per row:
         id = sha1(f"{SCHEMA_NAME}|{TABLE_NAME}|{COLUMN_NAME}|{ZONE_NAME}|{EDC_MODEL_NAME}").hexdigest()
     - Upload in batches (e.g. 500) using SearchClient.upload_documents
     - Return (success_count, fail_count, message)
     - If index missing -> friendly message: "Index not found. Create/select a valid index."

  def get_index_stats(self, index_name: str) -> dict:
     - best-effort: document count if possible (SearchClient.get_document_count)
     - if not permitted, return {"note": "..."}.

Index schema requirements (Phase 1):
- Key field: id (SimpleField, Edm.String, key=True, filterable=True)
- Searchable fields: ZONE_NAME, EDC_MODEL_NAME, STEWARD, MAL_CODE, SCHEMA_NAME, TABLE_NAME, COLUMN_NAME,
  BUSINESS_NAME, BUSINESS_DESCRIPTION, DATA_TYPE, SECURITY_CLASSIFICATION_CANDIDATE, DATA_TREATMENT
- Filterable fields: SCHEMA_NAME, TABLE_NAME, PII, PCI, SECURITY_CLASSIFICATION_CANDIDATE, DATA_TREATMENT
- Keep exact casing of your source file headers if possible OR map into snake_case consistently.
  IMPORTANT: pick ONE strategy and use it everywhere.
  Recommendation: convert incoming headers to snake_case internal keys, but store in index as snake_case too.

========================================================
C) Metadata store uses selected index (runtime)
========================================================
Update app/metadata_store.py:
- AzureAISearchMetadataStore must accept index_name at runtime, not fixed globally.
- Implement:
   def retrieve(self, query: str, index_name: str, top_k: int) -> list[dict]
   - uses SearchClient(endpoint, index_name, credential)
   - returns normalized docs with stable keys used by the LLM prompt

If retrieval fails, raise a custom exception with a friendly reason
(e.g., missing endpoint, auth, index not found).

========================================================
D) NL→SQL pipeline updated to accept index selection
========================================================
Update app/nl2sql.py:
- handle_user_turn(user_text, conversation_state, selected_index: str, ...) -> returns updated state + messages
- For non-greeting:
   1) docs = metadata_store.retrieve(user_text, index_name=selected_index, top_k=config.AI_SEARCH_TOP_K)
   2) If docs empty => ask clarifying question and stop (do not guess tables)
   3) Build metadata context + call LLM to produce SQL JSON
   4) Validate SQL (read-only)
   5) Ask for confirmation before execution
   6) Execute against Azure SQL, show results inline in chat
   7) Append tool/data summary back to conversation for LLM follow-up

========================================================
E) Gradio UI refactor: Tabs + shared index state
========================================================
Update app/ui.py build_ui() to have TWO tabs:

TAB 1: "Chat"
- Components:
  - Dropdown: "Metadata Index" (choices populated from AISearchService.list_indexes())
  - Button: "Refresh Index List" (refreshes dropdown choices)
  - Chatbot(type="messages")
  - Textbox + Send
- State:
  - gr.State for selected_index (string)
  - gr.State for conversation messages (your internal app messages)
- Behavior:
  - On dropdown change: update selected_index state.
  - On Send: call nl2sql.handle_user_turn(..., selected_index=selected_index_state)
  - All returns to Chatbot must be list[{"role","content"}].

TAB 2: "Azure AI Search"
- Components:
  - Read-only textbox showing endpoint
  - Button: "List Indexes" (fills dropdown)
  - Dropdown: "Select Index"
  - Textbox: "New Index Name"
  - Button: "Create Index"
  - File upload: accepts .txt/.psv/.csv
  - Button: "Upload to Selected Index"
  - Status output (markdown or textbox)
  - Optional: stats output (doc count)

- Behavior:
  - "List Indexes": list indexes and update both the tab dropdown AND the chat tab dropdown choices (shared).
  - "Create Index": uses new index name; on success refresh index lists and select it.
  - "Upload": ingest into selected index; show success/fail counts; refresh stats.
  - If permissions error: show friendly instructions (no trace).

IMPORTANT UI DETAIL:
- Share the same "selected index" state between tabs:
  - If user selects index in Azure AI Search tab, chat tab dropdown should reflect it (and vice versa).
  - Use one shared gr.State + update both dropdowns in event outputs.

========================================================
F) Error handling: show user-friendly messages
========================================================
All Azure Search errors must be translated to actionable messages.
If you already have ErrorExplainer, use it; otherwise implement small mapping:
- endpoint missing => "AI_SEARCH_ENDPOINT is not configured"
- index not found => "Selected index doesn't exist. Refresh and pick one."
- MSI multi-identity => "Multiple managed identities exist; set AI_SEARCH_MANAGED_IDENTITY_CLIENT_ID (or AZURE_CLIENT_ID)."
- forbidden => "You don't have permission to create indexes or upload docs. Ask admin for Search Index Data Contributor."

Never show tokens, connection strings, or stack traces in UI.

========================================================
G) Tests (mock Azure, no network)
========================================================
Add tests:
1) tests/test_ai_search_service_list_indexes.py
  - mock SearchIndexClient.list_indexes to return objects with name
2) tests/test_ai_search_service_ingest_psv.py
  - feed a small pipe-separated file (use tmp_path)
  - ensure csv delimiter='|'
  - ensure id is created and upload_documents called with batch list
3) tests/test_ui_index_state_sync.py
  - unit test the handler functions that update both dropdowns share same selection
4) tests/test_nl2sql_uses_selected_index.py
  - metadata_store.retrieve called with selected_index argument

Acceptance criteria:
- In UI, user can list indexes, create index (if permitted), upload pipe-separated file to that index.
- In Chat tab, user can select index from dropdown and retrieval uses that index.
- Dropdown choices refresh correctly.
- App does not crash on auth/permission errors; it shows understandable text.
- Chatbot always receives list[{"role","content"}].
- pytest -q passes.
Deliver full updated contents for all modified/new files.
