# Step 4 — Azure AI Search: ensure indexes + upload metadata docs (MSI auth)

## Goal
Upload the JSONL docs created in Step 3 into Azure AI Search, using Managed Identity auth.
Indexes:
- meta_data_field
- meta_data_table
- meta_data_relationship

Input files:
- out/field_docs.jsonl
- out/table_docs.jsonl
- out/relationship_docs.jsonl

Rules:
- If an index exists, DO NOT recreate it.
- If missing, create it.
- Then upload/merge docs.
- Keep the index schema minimal (NO vector fields yet) to ship fast.

---

## What to implement (Copilot: do exactly this)

### 1) Create a new script
Create file: `scripts/search_upload_metadata.py`

### 2) Define these classes / functions (exact names + signatures)

#### Dataclass: `AppConfig`
Attributes:
- `search_endpoint: str`  (from env `AZURE_SEARCH_ENDPOINT`)
- `client_id: str | None` (from env `AZURE_CLIENT_ID`, optional)
- `index_field: str = "meta_data_field"`
- `index_table: str = "meta_data_table"`
- `index_relationship: str = "meta_data_relationship"`
- `file_field: str = "out/field_docs.jsonl"`
- `file_table: str = "out/table_docs.jsonl"`
- `file_relationship: str = "out/relationship_docs.jsonl"`
- `batch_size: int = 500`
- `validate_top_k: int = 3`

#### Function: `load_config() -> AppConfig`
- Reads env vars
- Validates `search_endpoint` not empty
- Returns `AppConfig`

#### Function: `get_credential(cfg: AppConfig)`
- If `cfg.client_id` is set -> `ManagedIdentityCredential(client_id=cfg.client_id)`
- Else -> `DefaultAzureCredential()`

#### Function: `read_jsonl(path: str) -> list[dict]`
- Reads JSONL file
- Returns list of dicts
- Raises with a clear error if file missing/empty

#### Function: `chunk_list(items: list, size: int) -> list[list]`
- Splits into batches

#### Function: `index_exists(index_client: SearchIndexClient, index_name: str) -> bool`
- Uses `list_index_names()` (or equivalent)

#### Function: `build_index_definition(index_name: str) -> SearchIndex`
- Returns the correct SearchIndex object for a given index name
- Must support exactly these 3 index names
- Any other name -> raise ValueError

#### Function: `ensure_index(index_client: SearchIndexClient, index_name: str) -> None`
- If exists -> print: `Index exists: <name> (skip create)`
- Else -> create index from `build_index_definition()` and print: `Created index: <name>`

#### Function: `upload_docs(search_client: SearchClient, docs: list[dict], batch_size: int) -> dict`
- Upload via `merge_or_upload_documents()` (preferred) else `upload_documents()`
- Upload in batches
- Returns summary dict:
  - `{"attempted": int, "succeeded": int, "failed": int, "errors": list[str]}`

#### Function: `validate_search(search_client: SearchClient, query: str, top_k: int) -> None`
- Executes a search
- Prints top_k results:
  - `id`
  - first 120 chars of `content`

#### Function: `main() -> int`
- Orchestrates:
  - load_config
  - get_credential
  - create SearchIndexClient
  - for each index: ensure_index
  - for each index: read_jsonl -> upload_docs
  - validation searches
- Returns 0 for success, non-zero for failure

---

### 3) Azure AI Search index schemas (minimal, no vectors)

#### Common required fields for ALL indexes
- `id` (key, Edm.String, filterable)
- `content` (Edm.String, searchable)

#### Index: `meta_data_field`
Fields:
- mal_code (Edm.String)
- schema_name (Edm.String, filterable)
- table_name (Edm.String, filterable)
- column_name (Edm.String, filterable)
- security_classification_candidate (Edm.String)
- pii (Edm.Boolean, filterable)
- pci (Edm.Boolean, filterable)
- business_name (Edm.String, searchable)
- business_description (Edm.String, searchable)
- data_type (Edm.String)
- is_key (Edm.Boolean, filterable)
- is_filter_hint (Edm.Boolean, filterable)
- allowed_values (Edm.String, searchable)
- notes (Edm.String, searchable)

#### Index: `meta_data_table`
Fields:
- schema_name (Edm.String, filterable)
- table_name (Edm.String, filterable)
- table_business_name (Edm.String, searchable)
- table_business_description (Edm.String, searchable)
- grain (Edm.String)
- primary_keys (Edm.String)
- default_filters (Edm.String)
- notes (Edm.String, searchable)

#### Index: `meta_data_relationship`
Fields:
- from_schema (Edm.String, filterable)
- from_table (Edm.String, filterable)
- to_schema (Edm.String, filterable)
- to_table (Edm.String, filterable)
- join_type (Edm.String)
- join_keys (Edm.String, searchable)
- cardinality (Edm.String)
- relationship_description (Edm.String, searchable)
- active (Edm.Boolean, filterable)

Notes:
- Do NOT add vector fields in this step.
- Use only built-in Search fields (SimpleField / SearchField).

---

### 4) Upload behavior
- Load JSONL docs from:
  - `out/field_docs.jsonl`
  - `out/table_docs.jsonl`
  - `out/relationship_docs.jsonl`
- Upload using merge-or-upload
- Batch size: 500
- Print per-index upload summary:
  - attempted, succeeded, failed
  - print first 5 errors if any

---

### 5) Quick validation searches
After upload, run:
- meta_data_field: search `"agreement"` OR `"RRDW"`
- meta_data_table: search `"transaction"`
- meta_data_relationship: search `"JOIN"`
Print top 3 results (id + snippet)

---

## Run instructions (I will run these)
1) Set env vars:
   - `AZURE_SEARCH_ENDPOINT="https://<your-service>.search.windows.net"`
   - (optional) `AZURE_CLIENT_ID="<user-assigned-msi-client-id>"`

2) Run:
- `python scripts/search_upload_metadata.py`

---

## Acceptance criteria
- Script runs without errors
- Indexes exist (created only if missing)
- Docs uploaded to all 3 indexes
- Validation searches print results for each index
