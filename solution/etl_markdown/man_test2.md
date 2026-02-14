Fix scripts/load_excel_to_sqlite.py crash: NameError: os is not defined.

1) Open scripts/load_excel_to_sqlite.py
2) Ensure these imports are the very first lines in the file (before any sys.path insert):
   import os
   import sys
3) Immediately after those imports, keep the sys.path bootstrap (can stay as-is):
   sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

4) Re-run:
   /app1/tag5916/projects/text2sql_v2/.venv/bin/python scripts/load_excel_to_sqlite.py

Return the full console output.
