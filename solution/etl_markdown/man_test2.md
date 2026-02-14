We now have:
IndentationError: expected an indented block after 'try' statement on line 14
File: scripts/load_excel_to_sqlite.py (error points at/near a sys.path.insert line)

DO NOT add new features. Fix ONLY this syntax/indentation issue and keep the script runnable.

TASK
1) Open scripts/load_excel_to_sqlite.py and fix indentation so it parses.
2) There must be exactly ONE sys.path.insert block, and it must be:
   - at the very top of the file (module level)
   - NOT inside any try/except, function, or class
3) Remove any stray/duplicate sys.path.insert lines elsewhere in the file.
4) Ensure any `try:` has a properly indented body (or remove the try if it’s not needed).
5) After fixing, run:
   PYTHONUNBUFFERED=1 /app1/tag5916/projects/text2sql_v2/.venv/bin/python -m py_compile scripts/load_excel_to_sqlite.py
   (this must succeed)
6) Then run:
   PYTHONUNBUFFERED=1 /app1/tag5916/projects/text2sql_v2/.venv/bin/python -u scripts/load_excel_to_sqlite.py
7) Paste the full output.

Implementation guidance (minimal + safe):
- Put these imports first: `import os, sys`
- Immediately after, add sys.path insert once:
  sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
- Then all other imports.
- Then main()/if __name__ guard as previously planned.

Now do steps 1–7 and paste results.
