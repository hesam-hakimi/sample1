## Step 4 — Run the uploader and capture output

### 1) Quick sanity check (file exists)
Run:
- `ls -la scripts/search_upload_metadata.py`
- `ls -la out/*.jsonl`

Expected:
- `out/field_docs.jsonl`, `out/table_docs.jsonl`, `out/relationship_docs.jsonl` all exist

---

### 2) Set env vars (same terminal session)
Run (replace values):
- `export AZURE_SEARCH_ENDPOINT="https://<your-service>.search.windows.net"`
- `export AZURE_CLIENT_ID="<your-user-assigned-msi-client-id>"`

If you do NOT have a user-assigned client id, skip the second line.

---

### 3) Run the script and capture FULL output
Run:
- `python scripts/search_upload_metadata.py`

### 4) Paste back here
Paste:
1) the full console output  
2) if it fails: the full stack trace  
3) if it succeeds: the validation search output lines (top 3 results per index)
