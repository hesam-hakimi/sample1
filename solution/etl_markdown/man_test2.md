 ## Next step: “0 rows fallback” (post-execution intelligence)

### Goal
When SQL executes successfully but returns **0 rows**, the app should:
1) **Diagnose** why (common: invalid filter value like `TERR_CD = 'US'`).
2) Either **ask a clarifying question** OR **auto-refine the SQL** (1–5 retries max) based on real data distributions.
3) Never loop forever; stop if no improvement or same SQL repeats.

---

## What to change (high level)
Search the repo for the “query orchestration” flow (likely `app/main_cli.py` → orchestrator/service → `app/core/sql_service.py` + `llm_service.py`).

Implement **one hook** after SQL execution:
- If `error is None` AND `row_count == 0` → run “empty result handler”.

---

## Required new data structure
Create a dataclass `QueryResult` (new file OK, e.g., `app/core/types.py` or `app/core/models.py`):

**QueryResult attributes**
- `question: str`
- `sql: str`
- `columns: list[str]`
- `rows: list[dict] | list[tuple]`  (keep whatever your executor returns)
- `row_count: int`
- `error: str | None`
- `warnings: list[str]` (ex: “0 rows fallback invoked”)
- `attempt: int` (0..MAX_RETRIES)
- `debug: dict | None` (put diagnostics here; only printed when DEBUG=true)

Acceptance: all SQL execution returns a `QueryResult`, even on failure.

---

## Required new helper: Empty result diagnostics
Create a helper class or module (name suggestion):
- `SqlEmptyResultAnalyzer` in `app/core/sql_analyzer.py`

**Inputs**
- `sql: str`
- `db_type: str` (for now default `"sqlite"`)
- `max_values: int` (default 30)

**Outputs (a dict)**
- `where_columns: list[str]` (columns used in WHERE)
- `literals: list[str]` (string/number literals used in WHERE if you can parse them)
- `column_profiles: dict[col -> profile]` where `profile` includes:
  - `null_or_blank_count: int`
  - `top_values: list[{"value": ..., "count": ...}]` (top N)
  - `has_us_like_values: bool` (specifically for strings: ‘US’, ‘USA’, ‘United States’ if present)
- `note: str` (short human summary like: “TERR_CD contains state/province codes; no US/USA values found”)

**How to implement diagnostics (SQLite-safe)**
- You don’t need a full SQL parser.
- Do a *best effort* extraction:
  - If the SQL contains `WHERE`, grab the substring between `WHERE` and (`GROUP BY`/`ORDER BY`/`LIMIT`/end).
  - Extract candidate column tokens like `TERR_CD`, `CTRY_NM`, etc. (simple regex is OK).
- For each detected column:
  - Run: `SELECT COUNT(*) FROM (<original_sql_without_limit>) WHERE <col> IS NULL OR TRIM(<col>) = ''` (if column is text; otherwise only IS NULL).
  - Run: `SELECT <col>, COUNT(*) c FROM (<base_table_or_sql_scope>) GROUP BY <col> ORDER BY c DESC LIMIT <max_values>`
- Keep it robust: if a diagnostic query fails, store the error in `debug` and continue.

Acceptance: for the user example (`TERR_CD`), analyzer prints a distribution similar to what you already showed (VT, FL, …, QC/ON, and “no US-like values”).

---

## Required new behavior: Empty result handler
Update the orchestrator (or wherever you run: LLM → SQL → execute → render) with this logic:

### Trigger
If `QueryResult.error is None` AND `QueryResult.row_count == 0`:

### Steps
1) Run `SqlEmptyResultAnalyzer` and attach output to `QueryResult.debug["empty_result_diagnostics"]`.
2) Decide next action via LLM **or** ask user:
   - If diagnostics strongly suggest “invalid literal value” (example: `TERR_CD` doesn’t contain `US/USA`) → prefer **clarifying question** unless the question clearly implies a safe relaxation.
3) If you choose auto-refine:
   - Call LLM with a “refine SQL after 0 rows” prompt.
   - Must return **one SQL statement only** (no markdown fences).
   - Re-run execution and repeat up to `MAX_RETRIES` (your env says 5 max).
4) Stop conditions:
   - Same SQL repeats (exact match after normalization) → stop and ask clarifying question.
   - Still 0 rows after MAX_RETRIES → stop and ask clarifying question.
   - Any SQL execution error → follow existing error-handling retry rules.

### Clarifying question format (CLI-friendly)
Return a message like:
- “Your filter `TERR_CD = 'US'` returns 0 rows. In this dataset, `TERR_CD` looks like state/province codes (VT, FL, …). Do you want:
  A) all clients in any US state (exclude Canadian provinces like QC/ON),
  B) clients where `CTRY_NM` indicates United States (if that column exists),
  C) remove the country filter and just list clients?”

(Keep it short; include top 10 values only when DEBUG=true.)

---

## LLM prompt changes (refine-after-0-rows)
Find the place where you prompt the model for SQL generation.
Add a second prompt template used only for the 0-rows retry:

**Must include**
- The user question
- The previous SQL
- The empty-result diagnostics summary + top values for relevant columns
- Hard rules:
  - output SQL only (no ``` fences)
  - use only known tables/columns from metadata
  - keep LIMIT <= configured default
  - prefer asking a clarifying question (return a special marker) when the intent is ambiguous

**Implementation detail**
- If the model returns a “clarify” marker (e.g., `CLARIFY: ...`) then **do not execute SQL**; just show the question to the user.

Acceptance: for “based in usa”, the app either:
- asks the clarifying question, OR
- changes the filter away from `TERR_CD='US'` to something that can return rows (based on diagnostics).

---

## Debug gating (IMPORTANT)
You asked for an inline panel but disabled unless debug.
So:
- All diagnostic dumps (top values lists, raw analyzer queries) should only print when `DEBUG=true`.
- In non-debug, show only a short explanation + clarifying question.

---

## Tests to run (you execute; paste output back)
After implementation, run:

1) A query that should return rows:
- `python -m app.main_cli "show me 10 rows from v_dlv_dep_prty_clr"`

2) The “0 rows” scenario:
- `python -m app.main_cli "show me the list of all clients who are based in usa"`

**Expected**
- No crash.
- Either:
  - a clarifying question, OR
  - an auto-refined SQL that returns rows.
- No repeated infinite retries; max 5.

Paste:
- CLI output (full)
- If DEBUG=true, also paste the diagnostics section.
