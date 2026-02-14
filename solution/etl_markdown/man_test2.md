## Fix Step 5 config mismatch (accept AZURE_* env var names)

### Problem
`load_config()` currently requires:
SEARCH_ENDPOINT, OPENAI_ENDPOINT, OPENAI_API_VERSION, OPENAI_DEPLOYMENT
But our `.env` uses:
AZURE_SEARCH_ENDPOINT, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION, AZURE_OPENAI_DEPLOYMENT

### Required change
In `app/core/config.py`, update `load_config()` so it accepts BOTH naming styles:
- Prefer AZURE_* if present
- Otherwise fall back to non-AZURE names

### Mapping (must implement)
- search endpoint:
  - AZURE_SEARCH_ENDPOINT -> cfg.search_endpoint
  - else SEARCH_ENDPOINT

- openai endpoint:
  - AZURE_OPENAI_ENDPOINT -> cfg.openai_endpoint
  - else OPENAI_ENDPOINT

- api version:
  - AZURE_OPENAI_API_VERSION -> cfg.openai_api_version
  - else OPENAI_API_VERSION

- deployment:
  - AZURE_OPENAI_DEPLOYMENT -> cfg.openai_deployment
  - else OPENAI_DEPLOYMENT

- MSI client id:
  - AZURE_CLIENT_ID if present -> cfg.azure_client_id
  - else CLIENT_ID (optional)

### Validation
Only raise "Missing required env vars" if neither option exists for each required field.

### After patch
Run:
- `python -c "from app.core.config import load_config; print(load_config())"`
Paste the output or any stack trace.
