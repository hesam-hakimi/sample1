GOAL (Step 4): Make the end-to-end CLI work by (A) importing the hashed Excel into SQLite and (B) preventing markdown fences (```sql) from reaching sqlite execution.

CONSTRAINTS / NOTES
- Do NOT change the existing Excel file structure.
- Excel file is in ./data and its name contains spaces: "Hashed data _v2.xlsx" (confirm exact filename).
- We already have meta indexes in Azure AI Search; now we need real data in SQLite so SQL execution can succeed.
- LLM is currently returning SQL wrapped in markdown fences, causing sqlite error near ```sql.
- Keep changes minimal, robust, and easy to switch later from SQLite to Azure SQL.

PART A — IMPORT EXCEL -> SQLITE
1) First, confirm the exact Excel filename and sheet names:
   - Add a small command or script output that prints:
     - resolved excel path
     - list of sheet names exactly as found
   - If the filename has awkward whitespace/newlines, rename it to a clean name (e.g., hashed_data_v2.xlsx) ONLY if safe, and update references accordingly.

2) Create a new script: scripts/load_excel_to_sqlite.py
   It must define:
   - class ExcelToSQLiteLoader
     - __init__(self, excel_path: str, sqlite_path: str, if_exists: str="replace", debug: bool=False)
     - list_sheets(self) -> list[str]
     - derive_table_name(self, sheet_name: str) -> str
       RULE: use the LAST token after '.' so:
         "rrdw_dlv.v_dlv_dep_prty_clr" -> "v_dlv_dep_prty_clr"
       Also sanitize to sqlite-friendly: keep only [A-Za-z0-9_], replace others with '_'.
     - load_all_sheets(self) -> dict
       Loads each sheet into sqlite table with derived name.
       Prints a summary: table_name, rows, columns.
     - validate(self) -> None
       Runs sqlite queries:
         - list tables
         - select count(*) from each imported table

3) SQLite location:
   - Use existing config loader (app.core.config.load_config()) to get SQLITE_PATH
   - Default should remain local_data.db (or whatever config says)
   - Ensure the script can be run like:
       /app1/.../.venv/bin/python scripts/load_excel_to_sqlite.py
     and it imports everything from ./data Excel into that sqlite file.

4) Dependencies:
   - Use pandas + openpyxl.
   - Use sqlite3 directly OR SQLAlchemy, whichever is simplest in this environment.
   - Update requirements.txt only if needed.

PART B — STRIP MARKDOWN FROM LLM SQL (NO ```sql IN EXECUTE)
5) Locate where SQL text is extracted from the LLM response (likely in app/services/llm_service.py).
   Add a dedicated function:
   - def extract_sql(text: str) -> str
     Behavior:
     - Remove triple backtick blocks (```sql ... ``` and ``` ... ```)
     - If the response contains extra commentary, return ONLY the SQL statement.
     - Trim whitespace.
     - Do NOT return surrounding quotes.
     - If multiple statements are present, keep the first non-empty SQL statement.

6) Ensure the sqlite execution path calls extract_sql() before cur.execute(sql).
   - Add debug logging (only when DEBUG=true) to print:
     - raw llm response (or first 500 chars)
     - extracted_sql (final)

PART C — RUN + REPORT BACK
7) Run in this order and paste outputs:
   a) /app1/.../.venv/bin/python scripts/load_excel_to_sqlite.py
      (show sheet list + import summary + validation counts)
   b) /app1/.../.venv/bin/python -m app.main_cli "show me the list of all clients who are based in usa"
      (paste full output / stacktrace if any)

IMPORTANT
- Do not implement UI changes in this step.
- Keep changes small and explicit.
- If you introduce any new functions/classes, list them at the end of your response with their file path and purpose.
