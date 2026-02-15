# Copilot Prompt — Backend-first: Event Streaming + Tests (UI comes later)

> **Do NOT implement any Streamlit/UI changes in this step.**  
> Focus on backend reliability + test coverage. After this passes, we will wire the same event stream into the UI.

## Goal

1) Add a **structured activity/event stream** to the backend that captures progress like:

- deciding whether tools are needed  
- calling AI Search  
- building prompt  
- generating SQL  
- sanitizing SQL (remove markdown fences)  
- validating SQL (basic)  
- executing SQL  
- **0-row fallback** diagnostics  
- errors/retries (max 5) decisions

2) Add **tests** to verify the stream + critical behaviors.

## Constraints (must follow)

- **No new agent frameworks** (keep it lightweight, pure Python).  
- Keep existing public APIs working; add new optional params rather than breaking changes.  
- Avoid new heavy dependencies. Use `pytest` if already present; otherwise add it.  
- Logging must be **structured** (events), not just `print()`.

## Quick repo scan (do this first)

Search the repo for these files/classes and note current signatures:
- `app/main_cli.py` (CLI entry)
- `app/core/llm_service.py` (LLM calls + response_format handling)
- `app/core/sql_service.py` (SQLite execution)
- `app/core/query_orchestrator.py` OR `app/core/orchestrator.py` OR similar (router/orchestrator)
- `app/core/query_result.py` (already introduced for 0-row fallback)
- `app/core/ai_search_service.py` or similar (Azure AI Search tool integration)

If some names differ, **adapt the changes to the actual structure** but keep the intent.

---

## New backend types to add (signatures)

### 1) `app/core/events.py`

Create these types:

**`LogEvent` (dataclass)**
- `ts: datetime` (UTC)
- `stage: str`  (examples: `planner`, `ai_search`, `prompt`, `llm`, `sql_sanitize`, `sql_validate`, `sql_execute`, `fallback`, `retry`, `error`)
- `message: str`
- `level: str` (one of: `info`, `warning`, `error`)
- `data: dict | None` (optional structured payload)

**`EventSink` (protocol / interface)**
- `emit(self, event: LogEvent) -> None`

**`NullEventSink`**
- does nothing

**`ListEventSink`**
- stores events in-memory for tests (`events: list[LogEvent]`)

Optionally add:
- `emit_info(stage, message, data=None)`
- `emit_warn(...)`
- `emit_error(...)`

### 2) Extend `QueryResult` (or create a wrapper response)

You already have `QueryResult`. Update it (non-breaking) to include:

- `assistant_message: str | None`  (final user-facing response)
- `sql: str | None`
- `rows: list[dict] | None`  (or your existing format)
- `row_count: int | None`
- `events: list[LogEvent]`  (copy from sink at end)

If you cannot safely change `QueryResult`, create a new dataclass (e.g., `OrchestratorResponse`) with the fields above and return that from the orchestrator **without breaking existing callers**.

---

## Orchestrator changes (core of this step)

Find the function that handles a user question end-to-end (router/orchestrator). Update it so:

### A) It accepts an optional event sink
Add a parameter:
- `event_sink: EventSink | None = None`
and inside do:
- `sink = event_sink or NullEventSink()`

### B) Emit events at each step
Emit at least:

1. `planner` — received question
2. `planner` — deciding tools needed
3. `ai_search` — if called: query + number of docs returned
4. `prompt` — building prompt (DO NOT log secrets)
5. `llm` — calling LLM, and LLM returned (include model/deployment name if safe)
6. `sql_sanitize` — before/after sanitization (do not log huge SQL; truncate)
7. `sql_validate` — validation success/fail reason
8. `sql_execute` — execution started + completed, include row_count
9. `fallback` — only when row_count == 0: discovered likely filter columns + top values
10. `error` — exceptions with safe message
11. `retry` — when you decide to retry (max 5), include reason + attempt number

### C) Fix “hi” / smalltalk producing no assistant message
If the user says something like `hi`, `hello`, `help`:
- return a friendly assistant_message and emit `planner` event
- do **not** attempt SQL execution
This should prevent the UI from showing “(No assistant message returned)”.

### D) SQL sanitization must be centralized
Ensure the final SQL passed to SQLite never contains:
- triple backticks
- leading “```sql”
- trailing “```”
Emit a `sql_sanitize` event showing that sanitization happened.

### E) Retry logic (model decides based on error)
Implement a retry loop (max 5):
- If LLM or tool call fails with a transient-ish error (timeout, rate limit, connection error), emit `retry` and retry.
- If SQL execution fails due to obvious SQL syntax issues, emit `error`, then:
  - call LLM once to “repair SQL” using the error message and schema context
  - emit `retry`
- Always stop after 5 attempts and return a helpful assistant_message.

---

## CLI wiring (backend-only)

Update `app/main_cli.py` so that:
- It creates a `ListEventSink`
- Passes it into orchestrator
- Prints events to console as they happen (or at end)
  - Format: `[stage] message` (keep it short)
- If assistant_message is empty/None, print a safe default.

> Keep CLI backwards compatible: existing command `python -m app.main_cli "question"` should still work.

---

## Tests (must add)

Create/extend tests under `tests/` using `pytest`.

### Test 1 — events are emitted for a normal query
- Use a **FakeLLM** that returns SQL like: `SELECT 1 as x LIMIT 1;`
- Use a **FakeSQLService** that returns 1 row
- Assert:
  - returned `assistant_message` is not empty
  - events include stages: `planner`, `llm`, `sql_sanitize`, `sql_execute`

### Test 2 — markdown fences are stripped
- FakeLLM returns:
  - ```sql
    SELECT 1;
    ```
- Assert SQL passed to executor has no backticks and no “sql” fence.

### Test 3 — 0-row fallback emits diagnostics
- FakeSQLService returns 0 rows
- Ensure `fallback` stage event exists and includes some `data` payload (e.g. `candidate_filters`, `top_values`)
- Ensure assistant_message includes a helpful explanation + suggestion

### Test 4 — “hi” returns assistant message and no SQL execution
- Input: `hi`
- Assert assistant_message is not empty
- Assert no `sql_execute` event exists

> If you already have a dependency injection approach, use it. If not, minimally refactor orchestrator to accept `llm_service` and `sql_service` as optional parameters to enable fakes in tests.

---

## Verification commands (run locally)

1) Run tests:
- `pytest -q`

2) Run CLI:
- `python -m app.main_cli "hi"`
- `python -m app.main_cli "show me 10 rows from v_dlv_dep_prty_clr"`

Expected:
- assistant_message printed
- event log shows meaningful stages
- no crashes

---

## Deliverables for this step

- `app/core/events.py` added
- orchestrator updated to accept `event_sink` and emit events
- `QueryResult` (or new response) includes `events`
- CLI prints/logs events and never returns empty assistant message
- tests added and passing

When done, paste:
- `pytest -q` output
- output of the 2 CLI commands above
- a short list of files changed
