NEXT STEP: End-to-end CLI smoke test (SQLite)

Goal
- Confirm the app can: (1) generate SQL for SQLite, (2) strip markdown/code fences, (3) execute successfully, (4) return rows.

Pre-check (must show evidence)
1) Verify SQLite DB exists and tables are present.
   Run ONE of these (whichever is available):

   Option A (sqlite3 CLI):
     sqlite3 local_data.db ".tables"

   Option B (python):
     /app1/tag5916/projects/text2sql_v2/.venv/bin/python -c "
     import sqlite3;
     con=sqlite3.connect('local_data.db');
     print(con.execute(\"select name from sqlite_master where type='table' order by 1\").fetchall());
     "

2) Confirm these tables exist (exact names):
   v_dlv_dep_agmt_clr
   v_dlv_dep_prty_agmt
   v_dlv_dep_prty_clr
   v_dlv_dep_tran

Run end-to-end CLI tests (paste full outputs)
3) Run:
   PYTHONUNBUFFERED=1 /app1/tag5916/projects/text2sql_v2/.venv/bin/python -m app.main_cli "show me 10 rows from v_dlv_dep_prty_clr"

4) Run:
   PYTHONUNBUFFERED=1 /app1/tag5916/projects/text2sql_v2/.venv/bin/python -m app.main_cli "show me the list of all clients who are based in usa"

What to capture
- For each run: generated SQL (after sanitization), and execution result (rows or summary).
- If it fails: paste full stack trace.

Important fix rule (only if you see this error)
- If SQLite fails with:
    sqlite3.OperationalError: near "```": syntax error
  then update ONLY the SQL extraction/sanitization in LLMService so that:
  - removes triple backticks and optional language tags like ```sql
  - removes any leading/trailing backticks
  - returns plain SQL only (no markdown)
  After patching, re-run steps 3 and 4 and paste outputs.

Do NOT add new features. Only patch what is needed for the smoke test to pass.
