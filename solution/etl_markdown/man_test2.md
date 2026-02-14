# Step 5 — Build the “Query Orchestrator” module (no UI yet)

## Goal
Create a backend module that can answer a question end-to-end:
User Question -> AI Search (metadata) -> GPT SQL -> SQLite execute -> (optional GPT interpretation) -> Final Answer

Keep it robust, with logging + retry rules, and designed so we can swap SQLite -> Azure SQL next week.

---

## Create these files (exact names)
1) `app/core/config.py`
2) `app/core/logger.py`
3) `app/core/search_service.py`
4) `app/core/sql_service.py`
5) `app/core/llm_service.py`
6) `app/core/orchestrator.py`
7) `app/main_cli.py`

---

## Required classes / functions (must match)

### A) app/core/config.py
Dataclass: `AppConfig`
Attributes:
- `debug: bool = False`
- `search_endpoint: str`
- `search_index_field: str = "meta_data_field"`
- `search_index_table: str = "meta_data_table"`
- `search_index_relationship: str = "meta_data_relationship"`
- `azure_client_id: str | None = None`   # MSI client id optional
- `openai_endpoint: str`                 # Azure OpenAI endpoint
- `openai_api_version: str`
- `openai_deployment: str`               # GPT model deployment name (gpt-4.1)
- `sqlite_path: str = "local_data.db"`
- `max_search_docs: int = 50`            # adjustable
- `max_retries: int = 5`                 # global retry cap
- `send_result_to_gpt: bool = True`      # new requirement toggle

Function: `load_config() -> AppConfig`
- load from `.env` using python-dotenv
- validate required fields are present
- return config

---

### B) app/core/logger.py
Function: `get_logger(debug: bool) -> logging.Logger`
- if debug=True: INFO logs + include exception stack traces
- else: only WARNING/ERROR

---

### C) app/core/search_service.py
Class: `SearchService`
Constructor:
- `__init__(self, cfg: AppConfig, logger: logging.Logger)`

Methods:
- `search_metadata(self, question: str, top_k: int) -> dict`
Return dict structure (exact keys):
{
  "field_hits": list[dict],
  "table_hits": list[dict],
  "relationship_hits": list[dict]
}

Each hit dict must include:
- `id: str`
- `score: float | None`
- `content: str`

Rules:
- Use MSI auth (ManagedIdentityCredential if client id else DefaultAzureCredential)
- Use SearchClient for each index
- Use simple text search first (search_text=question) — no vector yet
- top_k comes from cfg.max_search_docs (default 50)

---

### D) app/core/sql_service.py
Class: `SQLService`
Constructor:
- `__init__(self, cfg: AppConfig, logger: logging.Logger)`

Methods:
- `execute_sql(self, sql: str) -> dict`
Return dict (exact keys):
{
  "columns": list[str],
  "rows": list[list],
  "row_count": int
}

Rules:
- Use SQLite for now
- Must be implemented so we can later swap to Azure SQL (design it with a single entry point)

---

### E) app/core/llm_service.py
Class: `LLMService`
Constructor:
- `__init__(self, cfg: AppConfig, logger: logging.Logger)`

Methods:
1) `generate_sql(self, question: str, context: dict) -> str`
2) `interpret_result(self, question: str, sql: str, result: dict) -> str`

Rules:
- Use Azure OpenAI with MSI auth (like your working notebook)
- Must NOT use agentic libraries; just plain chat completions
- Must include retry with exponential backoff up to cfg.max_retries
- When generating SQL:
  - Return ONLY SQL (no markdown)
  - Prefer SELECT only
  - Add LIMIT/TOP to cap results (default 50) but allow cfg to control
- When interpreting:
  - Summarize result into a business-friendly answer
  - If result empty, say so and suggest next question

---

### F) app/core/orchestrator.py
Class: `QueryOrchestrator`
Constructor:
- `__init__(self, cfg: AppConfig, logger: logging.Logger, search: SearchService, llm: LLMService, sql: SQLService)`

Method:
- `answer(self, question: str) -> dict`
Return dict (exact keys):
{
  "question": str,
  "search_context": dict,
  "generated_sql": str,
  "sql_result": dict,
  "final_answer": str,
  "debug": dict
}

Rules:
- Steps:
  1) call search.search_metadata(question, cfg.max_search_docs)
  2) call llm.generate_sql(question, context)
  3) sql.execute_sql(generated_sql)
  4) if cfg.send_result_to_gpt: llm.interpret_result(...)
     else: final_answer = "SQL executed successfully."
- Debug dict must include (when cfg.debug=True):
  - top few retrieved contents
  - sql execution time
  - any retries performed

---

### G) app/main_cli.py
Function: `main() -> int`
- Read question from CLI argument or input()
- Run orchestrator.answer()
- Print:
  - final_answer
  - generated_sql
  - (if debug) print debug details

---

## Acceptance criteria
1) Running:
   `python -m app.main_cli "show me deposit count by day"`
   produces:
   - A SQL statement
   - Executes in SQLite
   - Produces final_answer (if send_result_to_gpt=True)

2) Debug mode:
   setting DEBUG=true in .env prints logs + debug payload

---

## IMPORTANT
- Do NOT build UI yet.
- Do NOT add vector search yet.
- Keep dependencies minimal and compatible with restricted TD environment.
