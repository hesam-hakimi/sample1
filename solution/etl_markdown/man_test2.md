We now get this runtime error in the Gradio chat UI after sending any message (even "hi"):

Error: ('HYT00', '[HYT00] [Microsoft][ODBC Driver 18 for SQL Server] Login timeout expired (0) (SQLDriverConnect)')

Goal:
1) The app must NOT try to connect to SQL Server for greetings/smalltalk.
2) When SQL connectivity really is needed, failures must be handled gracefully with a clear, actionable error message (not a crash).
3) Add a quick “DB Health Check” path + tests (no real DB required).

Please implement the following changes.

A) Add “greeting / non-data” bypass (no DB call)
- In app/nl2sql.py (or the send handler in app/ui.py), detect greeting/smalltalk inputs:
  hi, hello, hey, thanks, good morning, etc. (case-insensitive; trim whitespace).
- If it’s greeting/smalltalk, return:
  kind="greeting", sql="", explanation="Hi! Ask me a banking question…", and DO NOT call metadata queries or db.execute_query.

B) Improve DB connection robustness + diagnostics
- In app/db.py, ensure connection is lazy (only connect inside execute_query / ping, not at import time).
- Normalize SQL_SERVER:
  - If it looks like Azure SQL (contains ".database.windows.net") ensure server string uses tcp:... and includes port 1433.
  - Example normalized server: "tcp:<server>.database.windows.net,1433"
- Add explicit connection timeout:
  - Add "Connection Timeout=15;" into the ODBC conn string.
  - Also pass `timeout=15` to pyodbc.connect if supported.
- Add `ping()` function that tries `SELECT 1` and returns (ok: bool, message: str).
- Catch pyodbc.Error and map common cases:
  - HYT00 / timeout -> “Cannot reach SQL Server (network/DNS/firewall/VNet). Check SQL_SERVER, port 1433, and that this host can reach the server.”
  - 28000 / login failed -> “Auth failed. Verify Managed Identity is available + SQL is configured for AAD + permissions exist.”
  - Provide the SQL_SERVER value in the message (but NEVER print secrets).

C) UI changes (graceful behavior)
- In app/ui.py:
  - If nl2sql returns sql="", show explanation in chat and do not attempt DB actions.
  - Add a small “Test DB Connection” button that calls db.ping() and shows the result in chat/status.
  - If execute fails, show the friendly mapped message in the chat and keep UI responsive.

D) Tests (no real DB)
- tests/test_nl2sql.py:
  - generate_sql("hi") returns kind="greeting" and does NOT call db.execute_query (mock it and assert not called).
- tests/test_db_errors.py:
  - Mock pyodbc.connect to raise pyodbc.Error with args containing "HYT00" and assert db.ping() returns ok=False with the friendly timeout message.
- tests/test_ui_logic.py:
  - Send handler with "hi" must not call db and must not error.

Acceptance criteria:
- Typing "hi" never triggers SQL connection attempts.
- If SQL is unreachable, the user sees an actionable message instead of raw pyodbc stack traces.
- A “Test DB Connection” button exists and works (with mocked tests).
- `pytest -q` passes.
- Return full updated content for any modified files.
