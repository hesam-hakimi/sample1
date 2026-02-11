We have a Gradio NL→SQL app. Now when user asks: "show me the list of tables in database",
the app errors with:

[Microsoft][ODBC Driver 18 for SQL Server][SQL Server] Invalid object name 'meta.Tables'. (208)

Goal:
1) App must not crash when metadata tables are missing.
2) App must show an actionable message and provide a safe setup path.
3) Add a safe fallback to list tables using system catalog (sys/information_schema) without requiring meta.*.

Constraints:
- Do NOT use OpenAI Runner/Agent.
- Keep the existing meta schema approach, but detect when it’s not initialized.
- Never run user-provided DDL. Only run bundled SQL scripts from repo when user clicks an explicit button.

Implement changes:

A) DB capability checks
- In app/db.py add:
  - def metadata_ready() -> tuple[bool, list[str]]:
      checks existence of:
      schema meta and tables: meta.Tables, meta.Columns, meta.Relationships, meta.BusinessTerms
      Use OBJECT_ID('meta.Tables') IS NOT NULL etc.
      Return (True, []) if all exist, else (False, ["meta.Tables", ... missing])
  - def list_all_tables() -> pandas.DataFrame:
      read-only query to list tables from sys catalog:
      SELECT s.name AS schema_name, t.name AS table_name
      FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id
      ORDER BY s.name, t.name;

B) Bootstrap / Initialize scripts (safe internal execution)
- Create app/bootstrap.py:
  - def run_sql_script_file(path: str) -> None
    Reads sql/*.sql and executes it via pyodbc.
    Must support splitting batches on lines containing only "GO" (case-insensitive).
    Must NOT accept arbitrary SQL from user; only file paths inside repo (whitelist).
- Add a single function:
  - def initialize_database() -> None:
      runs, in order:
        sql/01_create_banking_schema.sql
        sql/02_create_metadata_schema.sql
        sql/03_seed_sample_data.sql
    (only when user clicks UI button)

C) NL2SQL orchestration behavior
- In app/nl2sql.py:
  - Before doing any metadata queries, call db.metadata_ready()
  - If not ready:
    - If user question is about listing tables/schemas (“list tables”, “what tables exist”, etc),
      return kind="system_query" and sql set to the sys catalog query result (or directly return a DataFrame)
      WITHOUT touching meta.*
    - Otherwise return kind="error" with explanation:
      “Metadata tables not initialized in this database (missing: ...). Click ‘Initialize DB’ or run the sql scripts.”
    - Do not call LLM metadata plan step when meta is missing.

D) UI improvements
- In app/ui.py:
  - Add buttons:
    1) “Check Metadata” -> calls db.metadata_ready(), displays status in chat
    2) “Initialize DB” -> calls bootstrap.initialize_database() and reports success/failure in chat
    3) “List Tables” -> calls db.list_all_tables() and displays in the grid
  - When nl2sql returns kind="error", show the explanation and do not proceed.
  - When returning a DataFrame result (table list), show it in the results grid.

E) Tests (no real SQL)
- tests/test_metadata_ready.py:
  - Mock execute_query or pyodbc cursor so that OBJECT_ID checks return NULL or 1.
  - Verify metadata_ready returns missing object names.
- tests/test_list_tables.py:
  - Mock DB layer to return DataFrame; verify UI handler renders it.
- tests/test_nl2sql_meta_missing.py:
  - Mock metadata_ready() to False and ensure nl2sql.generate_sql does NOT attempt querying meta.* and does NOT call LLM for non-system questions.
- tests/test_bootstrap_runner.py:
  - Mock db connection/cursor to ensure run_sql_script_file splits on GO and executes batches.

Acceptance criteria:
- If meta.* is missing, app does not crash and tells user exactly what’s missing.
- “List tables” works even when meta.* is missing (uses sys catalog).
- “Initialize DB” runs bundled scripts only (safe), then meta.* queries work.
- pytest -q passes.
- Provide full updated content for any modified/new files.
