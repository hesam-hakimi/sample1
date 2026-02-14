## Update Step 4 to use `.env` + `python-dotenv`

### 1) Ask Copilot to add dependency
- Add `python-dotenv` to `requirements.txt`

Then run:
- `pip install -r requirements.txt`

### 2) Create `.env` at repo root (DO NOT COMMIT)
Add:
AZURE_SEARCH_ENDPOINT="https://<your-service>.search.windows.net"
AZURE_CLIENT_ID="<optional-user-assigned-msi-client-id>"

### 3) Update `scripts/search_upload_metadata.py`
At the very top of the file (before reading env vars), add:
- `from dotenv import load_dotenv`
- `load_dotenv()`  (optionally `load_dotenv(override=False)`)

### 4) Run
- `python scripts/search_upload_metadata.py`
add .env to .gitignore if it isn’t already.
