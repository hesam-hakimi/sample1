We ran:
  /app1/tag5916/projects/text2sql_v2/.venv/bin/python scripts/load_excel_to_sqlite.py
and got **no output**. I need this loader to be “loud”: always print progress + fail with a clear stack trace.

Do NOT redesign the project. Patch only scripts/load_excel_to_sqlite.py.

GOALS
1) Always print a start banner, paths being used, and progress per sheet.
2) If anything fails, print full traceback and exit non-zero.
3) After load, verify tables exist + print row counts.
4) Use the existing config loader if present (app.core.config.load_config). If not available, fall back to defaults.
5) Excel file is in ./data and name is exactly: "Hashed data_v2.xlsx" (note: may contain spaces; handle safely).
6) SQLite DB path should come from env/config (SQLITE_PATH). If not set, default to ./local_data.db.

REQUIRED CHANGES (in scripts/load_excel_to_sqlite.py)
A) Add a main() and guard:
   if __name__ == "__main__": raise SystemExit(main())
B) At the very top, ensure imports are ordered so sys.path bootstrap works and does not crash:
   import os, sys first, then sys.path insert, then the rest.
C) Add robust logging/prints:
   - print("LOAD_EXCEL_TO_SQLITE: START")
   - print resolved excel path + sqlite path
   - list sheet names before loading
   - for each sheet: print sheet name, rows, columns, target table name
   - after to_sql: print “OK”
D) Hard-fail early if Excel file does not exist (print helpful message).
E) Use pandas to read each sheet and write to SQLite:
   - Use dtype=str to avoid unexpected type coercion for hashed values.
   - Use if_exists="replace" (for now).
   - index=False.
F) Verification step at the end:
   - Connect to sqlite and query sqlite_master to list created tables.
   - For each created table: SELECT COUNT(*) and print the count.

RUN / VALIDATE (Copilot must run these commands and paste output)
1) From repo root:
   cd /app1/tag5916/projects/text2sql_v2
2) Confirm file exists:
   ls -lah "./data/Hashed data_v2.xlsx"
3) Run unbuffered so output always shows:
   PYTHONUNBUFFERED=1 /app1/tag5916/projects/text2sql_v2/.venv/bin/python -u scripts/load_excel_to_sqlite.py

PASTE BACK: full console output (including any traceback) + final list of created tables and counts.
