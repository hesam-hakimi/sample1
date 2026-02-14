## Step 5 — End-to-end run (SQLite + AI Search + GPT)

### 1) Run a simple test first (known sample-style question)
Run:
- `python -m app.main_cli "show me the list of all clients who are based in usa"`

### 2) If that fails because the SQLite tables don’t exist, quickly list tables
Run:
- `python -c "import sqlite3; c=sqlite3.connect('local_data.db'); print(c.execute(\"select name from sqlite_master where type='table' order by name\").fetchall())"`

Then rerun Step 1 using a question that matches an existing table name.

### 3) Paste back ALL console output
When you respond to me, include:
- generated_sql
- row_count
- final_answer
- debug section (since DEBUG=true)

### 4) If it fails
Paste the full stack trace.
Also run:
- `python -m app.main_cli "ping"`
and paste the output (this helps confirm the pipeline path).
