FIX STEP: Make scripts/load_excel_to_sqlite.py runnable without “No module named app”.

Goal:
- I want BOTH of these to work:
  1) /app1/tag5916/projects/text2sql_v2/.venv/bin/python scripts/load_excel_to_sqlite.py
  2) /app1/tag5916/projects/text2sql_v2/.venv/bin/python -m scripts.load_excel_to_sqlite

Required change:
1) Edit scripts/load_excel_to_sqlite.py:
   - At the very top (before importing app.*), add a safe sys.path bootstrap:
     - compute PROJECT_ROOT = parent directory of this script (…/text2sql_v2)
     - insert PROJECT_ROOT into sys.path if not present
   - Then import load_config using:
       from app.core.config import load_config

2) Add a main entry point:
   - def main() -> int:
       - load config
       - run the loader
       - return 0 on success, non-zero on failure
   - if __name__ == "__main__": raise SystemExit(main())

3) Do NOT change other modules for this fix.

After patch:
- Re-run:
  /app1/tag5916/projects/text2sql_v2/.venv/bin/python scripts/load_excel_to_sqlite.py
- Paste the full output.
