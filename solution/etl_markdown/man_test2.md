STEP 4 — Handle “0 rows” results + discover valid filter values (SQLite)

Context
- End-to-end flow works.
- Query “based in usa” generated WHERE TERR_CD='US' and returned 0 rows.
- We need the system to validate filter values against real data and recover gracefully.

Goal
When a SQL query returns 0 rows, the CLI should:
1) Detect empty result set
2) Identify the likely filter column(s) used (e.g., TERR_CD)
3) Run a lightweight “value discovery” query (top values + counts)
4) Ask the user a clarifying question with valid options (or suggest alternatives)

A) First: run diagnostics (no code changes yet)
From repo root, run these and paste outputs:

1) Show columns:
   sqlite3 local_data.db "PRAGMA table_info(v_dlv_dep_prty_clr);"

2) Check what values exist for TERR_CD:
   sqlite3 local_data.db "SELECT TERR_CD, COUNT(*) cnt FROM v_dlv_dep_prty_clr GROUP BY TERR_CD ORDER BY cnt DESC LIMIT 30;"

3) Check null/blank TERR_CD:
   sqlite3 local_data.db "SELECT SUM(CASE WHEN TERR_CD IS NULL OR TRIM(TERR_CD)='' THEN 1 ELSE 0 END) AS null_or_blank, COUNT(*) AS total FROM v_dlv_dep_prty_clr;"

4) Search for any “US-like” values:
   sqlite3 local_data.db "SELECT TERR_CD, COUNT(*) cnt FROM v_dlv_dep_prty_clr WHERE UPPER(TERR_CD) LIKE '%US%' GROUP BY TERR_CD ORDER BY cnt DESC LIMIT 30;"

B) Implement “0 rows fallback” in backend (minimal change, no new dependencies)
Create/Update these components (be explicit in code so we can modify later):

1) New dataclass:
   - File: app/core/query_result.py
   - class QueryResult:
       - sql: str
       - rows: list[dict] (or list[tuple])
       - row_count: int
       - columns: list[str]
       - execution_ms: float | None
       - error: str | None

2) Add a post-execution hook:
   - Where: after SQL execution returns results (likely in app/main_cli.py or_
