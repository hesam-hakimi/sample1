# AMCB TEXT2SQL (MSI-only)

This package contains a working, **MSI-only** (no API keys, no `az login`) Text-to-SQL demo:
- Gradio UI (modern TD-like style)
- Azure AI Search retrieval over metadata (fields + tables + relationships)
- Azure OpenAI (Entra ID / MSI token) for SQL generation + embeddings
- SQLite execution with **schema stripping** (SQLite has no schemas)
- Safer behavior: refuses to hallucinate columns/tables; asks clarification instead.

## Files
- `main.py` : app entrypoint
- `ui.py` : Gradio UI
- `ai_utils.py` : Azure Search + Azure OpenAI (MSI) + prompt logic
- `db_utils.py` : SQLite/SQLAlchemy helpers + fail-fast to avoid accidental "appdb" creation
- `create_meta_data_vector_index.py` : build/drop/create & upload v3 index from json/jsonl inputs
- `td_style.css` : UI styling
- `.env.example` : env template

## Quick start
1) Copy `.env.example` to `.env` and fill values.
2) Create/search index:
   ```bash
   python create_meta_data_vector_index.py
   ```
3) Run the app:
   ```bash
   python main.py
   ```

## Required roles (MSI)
Your VM/compute managed identity must have:
- **Azure AI Search**: `Search Index Data Contributor` (create/update index & upload) and `Search Index Data Reader` (query)
- **Azure OpenAI**: `Cognitive Services OpenAI User` (or equivalent for token auth)

