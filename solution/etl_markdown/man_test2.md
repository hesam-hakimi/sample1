# Refactor: Two‑Phase LLM Router (Plan → Tools → Answer) for Text2SQL Streamlit App

You are GitHub Copilot working inside this repository. Implement the refactor described below **end‑to‑end** (code + tests + run verification).  
Goal: **Every user message goes to the Chat Completion model first** to produce a **structured Plan JSON**. The app then decides whether to call tools (Azure AI Search / SQL) based on that Plan. Finally, the app calls Chat Completion again to produce the final assistant message (with tool results merged in).

---

## Target behavior (must match)

### 1) Always call LLM for a Plan
When the user sends any input (including “hi”), the app must first call Chat Completion with a “planner” prompt and receive **JSON** like:

```json
{
  "decision": "DIRECT|CLARIFY|AI_SEARCH|SQL|AI_SEARCH_AND_SQL",
  "reason": "short rationale",
  "clarifying_question": null,
  "ai_search_query": null,
  "sql_goal": null,
  "constraints": {
    "max_rows": 50,
    "execution_target": "sqlite|oracle"
  }
}
```

### 2) App executes based on decision
- **DIRECT**: call Chat Completion again to answer directly (no tools).
- **CLARIFY**: return a clarification question to the UI (no tools).
- **AI_SEARCH**: call the AI search tool, then call Chat Completion to answer using the search results.
- **SQL**: (a) get schema context (via metadata search) if needed, (b) call Chat Completion to generate SQL, (c) run SQL tool, then call Chat Completion to answer using SQL + result.
- **AI_SEARCH_AND_SQL**: do AI search first (or parallel if safe), then SQL path, then final answer call with everything merged.

### 3) Streaming activity log
The UI must show a **streaming activity log** while the pipeline runs (planner → search → sql generation → sql execution → final answer).  
Each step emits `TraceEvent(stage=..., message=...)` and the UI re-renders those events live.

### 4) Greeting “hi” must not hit tools
When user says “hi/hello/thanks”, the Plan should return `decision="DIRECT"`, and the final answer should be a friendly greeting, **no SQL**, **no AI Search**.

---

## Critical fixes required (based on current failures)

### A) Fix TraceEvent constructor mismatch
Current crash: `TypeError: TraceEvent.__init__() got an unexpected keyword argument 'stage'`.

**Fix**: Standardize `TraceEvent` in **one place only** (`app/ui/models.py`). It must include `stage`.

**Required dataclass**
```py
@dataclass(frozen=True)
class TraceEvent:
    ts_iso: str
    stage: str
    message: str
    level: str = "info"  # optional, default
    data: dict | None = None
```

Then update **all call sites** to use exactly these field names.

### B) Remove duplicate UIOptions / models drift
If `UIOptions` exists in multiple files (e.g., `orchestrator_client.py`), remove duplicates and import from `app.ui.models` everywhere.  
Same for `ChatMessage`, `TurnResult`/`UIRunResult`, and `TraceEvent`.

### C) Ensure `from __future__ import annotations` appears only once at the top
Some tests failed with:
`SyntaxError: from __future__ imports must occur at the beginning of the file`.

**Rule**: If present, it must be the first statement (after optional module docstring), and only once per file.

---

## Files to refactor / create

### 1) `app/ui/models.py`  (single source of truth)
Must contain (and be used by all UI code):
- `UIOptions`
- `ChatMessage`
- `TraceEvent` (with `stage`)
- `TurnResult` (or `UIRunResult`) — pick one name and use everywhere consistently.

Recommended shapes:

```py
@dataclass(frozen=True)
class UIOptions:
    max_rows: int = 50
    execution_target: str = "sqlite"  # or "oracle"
    debug_enabled: bool = False

@dataclass(frozen=True)
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str
    ts_iso: str

@dataclass(frozen=True)
class TurnResult:
    assistant_message: str | None
    clarification_question: str | None
    sql: str | None
    df: "pd.DataFrame | None"
    error_message: str | None
    debug_details: str | None
```

### 2) `app/core/plan_models.py` (new)
Define planner output model + validation.
- `DecisionKind` enum
- `Plan` dataclass (or pydantic model) with fields shown in JSON.

Add:
- `Plan.from_json(text: str) -> Plan` that strictly validates and falls back safely (default to CLARIFY if invalid).

### 3) `app/core/llm_router.py` (new)
This is the orchestrator for the two-phase flow. It should implement:

```py
class LLMRouter:
    def plan(self, user_text: str, history: list[ChatMessage], options: UIOptions, trace_cb: TraceCallback|None) -> Plan: ...
    def answer_direct(self, user_text: str, history: list[ChatMessage], options: UIOptions, trace_cb: TraceCallback|None) -> str: ...
    def generate_sql(self, user_text: str, history: list[ChatMessage], schema_context: str, options: UIOptions, trace_cb: TraceCallback|None) -> str: ...
    def final_answer(self, user_text: str, history: list[ChatMessage], plan: Plan, tool_payload: dict, options: UIOptions, trace_cb: TraceCallback|None) -> str: ...
```

Implementation can reuse your existing `LLMService` if present, but keep the responsibilities clean:
- `plan()` must return **ONLY** a Plan JSON parsed into `Plan`.
- `answer_direct()` is a standard chat completion answer.
- `generate_sql()` returns SQL only (or JSON with `{ "sql": "..." }`).
- `final_answer()` returns assistant message using tool payload + plan.

### 4) Tool wrappers (reuse existing services)
Reuse:
- `SearchService` for AI search / metadata search
- `SQLService` for SQL execution

But **move all decision logic** into the Plan + router pipeline.

### 5) `app/ui/orchestrator_client.py` (refactor)
This class should become a thin facade that calls the new router pipeline and returns `TurnResult`.

Required signature:
```py
TraceCallback = Callable[[TraceEvent], None]

class OrchestratorClient:
    def run_turn(
        self,
        user_text: str,
        history: list[ChatMessage],
        options: UIOptions,
        trace_cb: TraceCallback | None = None,
    ) -> TurnResult:
        ...
```

### 6) `app/ui/state.py` (refactor, ensure these exist)
Must provide:
- `init_session_state()`
- `get_chat_history()` / `append_chat_message()`
- `get_trace_events()` / `append_trace_event()`
- `get_ui_options()` / `set_ui_options()`

Implementation must store keys in `st.session_state`:
- `"messages"`: list[ChatMessage]
- `"trace_events"`: list[TraceEvent]
- `"ui_options"` or separate keys for `max_rows`, `execution_target`, `debug_enabled`

### 7) `app/ui/streamlit_app.py` (refactor)
Must:
- Render transcript from `get_chat_history()`
- On input: append user message immediately; then call orchestrator once per input
- Provide a `trace_cb` that appends trace events and live-renders activity log (via placeholder container)
- Render SQL + dataframe (if present) under assistant message
- Show errors safely (no stack trace unless debug enabled)

---

## Planner + SQL generation prompts (must be deterministic & strict)

### Planner prompt rules
- Output **valid JSON only** (no markdown).
- Must set `decision` to one of the allowed values.
- For greetings/smalltalk/thanks/help: choose `DIRECT`.
- For ambiguous: choose `CLARIFY` and ask one short question.
- For data questions requiring DB: choose `SQL` (or `AI_SEARCH_AND_SQL` if schema is needed).
- Do not hallucinate table names; if unknown, set `sql_goal` and rely on schema search later.

### SQL generation prompt rules
- Output either raw SQL only, or JSON with `{ "sql": "..." }` (choose ONE approach and implement matching parser).
- Must respect `options.max_rows` (add `LIMIT` for sqlite, `FETCH FIRST n ROWS ONLY` for Oracle where appropriate).
- Never do destructive statements (no DROP/DELETE/UPDATE/INSERT).
- If schema context is insufficient, do not guess; return a clarification request instead.

---

## Pipeline algorithm (OrchestratorClient.run_turn)

Pseudo:

1. `trace("planner", "Deciding whether tools are needed...")`
2. `plan = router.plan(...)`
3. if `plan.decision == CLARIFY`: return TurnResult(clarification_question=...)
4. if DIRECT:
   - `trace("llm", "Answering directly...")`
   - `answer = router.answer_direct(...)`
   - return TurnResult(assistant_message=answer)
5. else:
   - tool_payload = {}
   - if AI_SEARCH in decision:
       `trace("ai_search", "Searching...")`
       tool_payload["ai_search"] = search_service.search(plan.ai_search_query, ...)
       `trace("ai_search_result", "Search complete")`
   - if SQL in decision:
       `trace("schema", "Gathering schema context...")`
       schema_ctx = search_service.search_metadata(user_text, ...)
       `trace("sql_generate", "Generating SQL...")`
       sql = router.generate_sql(user_text, history, schema_ctx, options, trace_cb)
       `trace("sql_execute", "Executing SQL...")`
       sql_result = sql_service.execute_sql(sql)
       tool_payload["sql"] = { "sql": sql, "rows": sql_result.rows, "columns": sql_result.columns, "row_count": sql_result.row_count }
   - `trace("final", "Composing final answer...")`
   - answer = router.final_answer(user_text, history, plan, tool_payload, options, trace_cb)
   - return TurnResult(assistant_message=answer, sql=sql, df=df_if_any)

---

## Tests (pytest) — required
Add/adjust tests to prevent regressions:

1. **Planner JSON parsing**: invalid JSON => falls back to CLARIFY.
2. **Greeting**: “hi” results in Plan decision DIRECT and no tool calls.
3. **TraceEvent signature**: constructing TraceEvent with `stage=` works.
4. **Import smoke test**: importing `app.ui.streamlit_app` does not raise.

Use monkeypatch to stub LLM calls and tool calls; do not hit network.

---

## Definition of Done
- `pytest -q` passes.
- `streamlit run app/ui/streamlit_app.py` loads without exceptions.
- Typing “hi”:
  - shows planner + answer traces
  - returns a friendly greeting
  - does **not** call SQL or AI search
- Data question:
  - shows traces: planner → (ai_search/schema) → sql_generate → sql_execute → final
  - shows SQL + dataframe when available

---

## Implementation notes / guardrails
- Prefer **one canonical model set** in `app/ui/models.py`.
- Make parsing strict and safe; never crash the app due to bad LLM JSON.
- Keep changes minimal but consistent; remove duplicate dataclasses.
- Keep logs/trace text short; avoid leaking secrets in trace messages.
- Preserve existing public APIs unless they are clearly broken; if you must rename, update all call sites + tests.

Now implement the full refactor.
