# Step 5 — Run end-to-end test + capture outputs

## 1) Confirm file structure exists
Run:
- `find app -maxdepth 3 -type f | sort`

Expected (at least):
- app/core/config.py
- app/core/logger.py
- app/core/search_service.py
- app/core/sql_service.py
- app/core/llm_service.py
- app/core/orchestrator.py
- app/main_cli.py

---

## 2) Update `.env` with ALL required values
Open `.env` and ensure these keys exist (values are examples):

### Debug
DEBUG=true
SEND_RESULT_TO_GPT=true

### Azure AI Search
AZURE_SEARCH_ENDPOINT="https://<your-service>.search.windows.net"
AZURE_CLIENT_ID="<optional-user-assigned-msi-client-id>"

### Azure OpenAI (GPT 4.1)
AZURE_OPENAI_ENDPOINT="https://<your-openai-resource>.openai.azure.com"
AZURE_OPENAI_API_VERSION="2024-12-01-preview"
AZURE_OPENAI_DEPLOYMENT="<your-gpt-4.1-deployment-name>"

### SQLite
SQLITE_PATH="local_data.db"

### Behavior
MAX_SEARCH_DOCS=50
MAX_RETRIES=5

Save the file.

---

## 3) Sanity import check
Run:
- `python -c "from app.core.config import load_config; print(load_config())"`

If this fails, paste the stack trace.

---

## 4) Run a real question (end-to-end)
Run:
- `python -m app.main_cli "show me deposit count by day"`

If you don’t have deposit tables yet in SQLite, use a question that matches your current sqlite tables, for example:
- `python -m app.main_cli "show me the list of all clients who are based in usa"`

---

## 5) Paste back EXACTLY these outputs
1) The full console output  
2) If it fails: full stack trace  
3) If it succeeds: show me:
   - generated_sql
   - row_count
   - final_answer
   - and the debug section (since DEBUG=true)
