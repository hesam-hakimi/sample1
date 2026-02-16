---
name: "Create pytest integration test using .env for Azure AI Search PII metadata routing"
description: >
  Add a best-practice pytest test that loads Azure AI Search configuration from a local .env file,
  runs the existing backend/CLI flow for "PII columns" questions, and verifies the output is correct and user-friendly.
argument-hint: |
  Repo assumptions (adjust paths if different):
    - CLI entrypoint: python -m app.main_cli "<question>"
    - AI Search wrapper: app/core/ai_search_service.py
    - Orchestrator/router: app/core/orchestrator.py (or app/llm_router.py)
    - QueryResult: app/core/query_result.py
  Env vars:
    - AZURE_SEARCH_ENDPOINT
    - AZURE_SEARCH_INDEX_META_DATA_FIELD (default: meta_data_field)
    - AZURE_SEARCH_KEY (key auth) OR AZURE_SEARCH_USE_AAD=1 (AAD auth)
tools: ["pytest", "python", "python-dotenv"]
handsoffs:
  - label: "unit_tester"
    agent: "copilot"
    prompt: |
      Implement this as a small PR. Add/modify tests and ensure they pass locally.
    send: |
      Create/modify:
        - tests/test_pii_metadata_ai_search_env_integration.py (new)
        - requirements-dev.txt or pyproject.toml (add python-dotenv if missing)
        - .env.example (new, placeholders only)
        - .gitignore (ensure .env is ignored)
        - (optional) docs/testing.md (short instructions)
---

# Goal
Create a pytest **integration** test that:
1) Loads local `.env` (developer machine only).
2) Runs the existing PII/metadata question path end-to-end (prefer CLI).
3) Verifies: **AI Search is used**, **SQL is NOT executed**, and the final answer is **user-friendly**.

# Hard requirements
- NEVER commit real secrets.
- `.env` must be in `.gitignore`.
- Test must **SKIP** automatically when required env vars are missing (so CI doesn’t fail).
- Mark the test: `@pytest.mark.integration`.

# Step-by-step

## 1) Add python-dotenv
If not present, add:
- requirements-dev.txt: `python-dotenv>=1.0`
OR
- pyproject.toml dev deps: `python-dotenv>=1.0`

## 2) Add `.env.example` (placeholders only)
Create at repo root:
- AZURE_SEARCH_ENDPOINT=https://<YOUR-SERVICE>.search.windows.net
- AZURE_SEARCH_KEY=<YOUR-KEY-OR-LEAVE-BLANK-FOR-AAD>
- AZURE_SEARCH_USE_AAD=0
- AZURE_SEARCH_INDEX_META_DATA_FIELD=meta_data_field
- (optional) AZURE_SEARCH_API_VERSION=2023-11-01

## 3) Create integration test file
Create `tests/test_pii_metadata_ai_search_env_integration.py` with:

### a) Load `.env`
Use:
- `from dotenv import load_dotenv`
- `load_dotenv(Path(__file__).resolve().parents[1] / ".env")`

### b) Skip when env vars are missing
Read:
- endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
- key = os.getenv("AZURE_SEARCH_KEY")
- use_aad = os.getenv("AZURE_SEARCH_USE_AAD", "").lower() in {"1","true","yes"}

Skip rules:
- if not endpoint: `pytest.skip("AZURE_SEARCH_ENDPOINT not set in .env")`
- if not key and not use_aad: `pytest.skip("Set AZURE_SEARCH_KEY or AZURE_SEARCH_USE_AAD=1 in .env")`

### c) Determine if index has PII docs (pre-check)
Prefer using your app service to avoid duplicating auth logic:
- `AISearchService.search_metadata(query="*", top_k=5, filter="pii eq 'Yes'")`
BUT your service might not accept `filter` yet (you hit an “unexpected keyword argument 'filter'”).
So implement this in a tolerant way:

**Rule:** The test must call a *known* signature.
- If your current `search_metadata` signature is `(query: str, top_k: int, **kwargs)`, fix it to accept `filter` and pass it through.
- If you can’t change the signature right now, do a simple keyword query instead:
  - query for: `"pii" OR "PII" OR "confidential" OR "email" OR "address"`
  - Then filter results in Python where `doc.get("PII") == "Yes"` (or similar).

If after pre-check there are 0 hits:
- Fail with a helpful message telling how to seed the index, e.g.:
  - `ALLOW_AI_SEARCH_SEED=1 python scripts/seed_meta_data_field_from_sqlite.py`
  - or whatever seeding script exists in your repo.

### d) Run the CLI end-to-end and assert output
Use `subprocess.run`:
- command: `[sys.executable, "-m", "app.main_cli", "show me the columns that have PII information"]`
- capture_output=True, text=True

Assertions:
- returncode == 0
- stdout does NOT contain "Traceback"
- stdout does NOT contain "TypeError"
- stdout contains a user-friendly message (non-empty)
- stdout indicates AI search path ran (if events printed): contains "[ai_search]"
- stdout does NOT indicate SQL executed: does NOT contain "[sql_execute]" (or your equivalent)

### e) Assert the happy path shows at least one field
When pre-check found PII docs, assert CLI output includes at least one field/table name from the pre-check docs.
Example:
- take first doc’s column/field name and assert it appears in stdout.

## 4) Ensure `.env` is ignored
Update `.gitignore` if missing:
- `.env`
- `.env.*` (optional)

## 5) Add docs
Add `docs/testing.md` (or README section):
- Copy `.env.example` → `.env`
- Fill in endpoint/key (or AAD)
- Run: `pytest -m integration -q`

# Acceptance criteria
- `pytest -q` passes (unit tests)
- `pytest -m integration -q`:
  - Skips cleanly if env not set
  - Passes when env set and index has PII docs
- No secrets committed
- Validates routing: AI Search used; SQL not executed
- Final user message is friendly (no raw SQL / stack traces)
