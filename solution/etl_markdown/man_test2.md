# Text2SQL Streamlit Chat UI — Fix tool-selection + streaming Activity Log (Copilot Prompt)

## Goal
Update the existing **Streamlit chat-first UI** so that:

1) **Greeting / small-talk (e.g., “hi”) does NOT trigger AI Search or SQL.**  
2) **AI Search and SQL act like tools** the LLM *may* call **only when needed**.  
3) The **Activity Log streams step-by-step** during execution, and **each step “fades”** (use Streamlit toasts for fade-out), while also keeping a persistent log in the page.  
4) The **assistant response + results** always appear in the chat area (not only in terminal logs).  
5) Preserve the overall architecture and UI (chat-first); do **not redesign** the app.

You must implement this with **explicit classes, methods, and signatures** as defined below. Don’t invent new names unless required by missing code; if you must add a new file, follow the naming and signatures exactly.

---

## Current observed issues (from screenshots)
- Typing **“HI”** triggers:
  - metadata search
  - SQL generation/execution
  - “Rows returned …”
  Even though this should be a pure greeting.
- Activity log is shown as a static list. Desired: stream steps in sequence with a fade effect (“Intent → fades → tool call → fades → …”).

---

## Non-negotiable behavior requirements

### A) Small-talk must short-circuit tools
If user text is **greeting / small talk / thanks / pleasantry**, the assistant must:
- respond directly (friendly short response),
- **no AI Search**, **no SQL**,
- activity log shows:
  - `[intent] greeting`
  - `[decision] skip_tools`
  - optionally `[assistant] responded`

Examples that must skip tools:
- "hi", "hello", "hey", "good morning"
- "thanks", "thank you"
- "how are you"
- "who are you"
- "help" (should show usage examples, not search)

### B) LLM decides tool usage for real questions
For non-trivial prompts (data questions), the system should decide whether to call:
- **AI Search** (metadata search)
- **SQL generation/execution**
as tools, based on context + chat history.

Important: This is “tool use”, not a hard-coded pipeline that always searches.

### C) Activity Log must “stream” and “fade”
Implement **two layers**:
1) **Transient steps**: show each event as a **toast** (`st.toast(...)`) so it fades automatically.
2) **Persistent log**: keep a chronological activity panel (e.g., inside an expander or a section) showing the full history.

Avoid repeating the same toast on reruns; each toast should show once per event id.

### D) No chain-of-thought disclosure
Do not print hidden reasoning. Activity log entries must be **short operational steps** like:
- “Intent: greeting”
- “Tool call: search metadata indexes”
- “Tool result: 12 tables found”
- “SQL generated”
- “SQL executing…”
- “Rows returned: 4”

---

## Required architecture (classes + signatures)

### 1) Data models
Create/ensure these dataclasses exist (preferred in `app/ui/models.py` or your existing equivalent).

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal, Optional

@dataclass
class UIOptions:
    max_rows: int = 50
    execution_target: Literal["sqlite", "oracle"] = "sqlite"
    debug_enabled: bool = False

@dataclass
class ChatMessage:
    role: Literal["user", "assistant", "system"]
    content: str
    ts_iso: str

@dataclass
class TraceEvent:
    event_id: str              # unique per event
    kind: str                  # "intent" | "decision" | "tool_call" | "tool_result" | "sql" | "error" | ...
    message: str               # short display string
    ts_iso: str
    transient: bool = True     # if True, show as toast + also append to persistent log
    payload: Optional[dict[str, Any]] = None

@dataclass
class TurnResult:
    assistant_message: str = ""
    clarification_question: str = ""
    sql: str = ""
    df: Any = None             # typically pandas.DataFrame, but keep Any
    error_message: str = ""
    debug_details: Optional[dict[str, Any]] = None
```

### 2) Intent & tool decision
Create/ensure file: `app/ui/search_decider.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from app.ui.models import ChatMessage, UIOptions

@dataclass
class SearchDecision:
    intent: str                 # "greeting" | "smalltalk" | "data_question" | "unknown"
    needs_search: bool
    needs_sql: bool
    reason: str                 # short explanation (NOT chain-of-thought)

class SearchDecider:
    def decide(self, user_text: str, history: list[ChatMessage], options: UIOptions) -> SearchDecision:
        ...
```

**Rules inside `decide(...)`:**
- Implement a **fast deterministic intent check** FIRST (regex/keyword).
  - If greeting/small-talk/help/thanks → return `needs_search=False`, `needs_sql=False`
- For other cases:
  - Use a **light LLM call** (or existing orchestrator LLM) to classify:
    - intent
    - needs_search
    - needs_sql
  - The LLM must output strict JSON (validated).

### 3) Tools
Create/ensure tools are isolated behind classes (in `app/core/tools.py` or `app/ui/tools.py` — choose one location and keep it consistent):

```python
class MetadataSearchTool:
    def search(self, query: str, options: UIOptions) -> dict:
        \"\"\"Return metadata docs, tables, columns, etc.\"\"\"
        ...

class SQLExecutorTool:
    def execute(self, sql: str, options: UIOptions):
        \"\"\"Execute SQL against sqlite/oracle and return a DataFrame-like object.\"\"\"
        ...
```

### 4) Orchestrator facade (single entrypoint per chat turn)
Create/ensure file: `app/ui/orchestrator_facade.py`

```python
from __future__ import annotations
from app.ui.models import ChatMessage, UIOptions, TurnResult, TraceEvent

class OrchestratorFacade:
    def __init__(self, *, search_tool, sql_tool, llm_client, search_decider):
        ...

    def run_chat_turn(
        self,
        user_text: str,
        history: list[ChatMessage],
        options: UIOptions,
        trace_cb,
    ) -> TurnResult:
        \"\"\"
        Main pipeline for ONE user turn.
        Emits TraceEvent via trace_cb(event).
        Must NOT always call AI search.
        \"\"\"
        ...
```

**Behavior inside `run_chat_turn(...)`:**
- 1) Call `search_decider.decide(...)`
  - Emit trace events:
    - kind="intent"
    - kind="decision"
- 2) If greeting/small-talk/help/thanks:
  - Generate assistant message directly (no tools)
  - Return TurnResult(assistant_message=...)
- 3) Else:
  - If `needs_search`:
    - call `MetadataSearchTool.search(...)`
    - emit `tool_call` and `tool_result` trace events
  - If `needs_sql`:
    - call LLM to generate SQL, using any retrieved metadata context
    - emit `sql` trace events
    - execute SQL via `SQLExecutorTool.execute(...)`
    - emit rows-returned event
  - Compose final assistant message (should be shown in chat).

### 5) Activity stream storage
Create/ensure file: `app/ui/activity_stream.py`

```python
from __future__ import annotations
from app.ui.models import TraceEvent

class ActivityStream:
    def __init__(self):
        self.events: list[TraceEvent] = []

    def append(self, ev: TraceEvent) -> None:
        self.events.append(ev)

    def all(self) -> list[TraceEvent]:
        return list(self.events)
```

Store the ActivityStream in **Streamlit session_state** so it survives reruns.

### 6) Streamlit UI must render chat + stream toasts
File: `app/ui/streamlit_app.py`

**Hard requirements:**
- Ensure `import streamlit as st` exists at the top.
- Ensure `main()` exists and is called.
- Ensure the main area **always** renders:
  - Title/header
  - Chat transcript (st.chat_message)
  - Chat input at bottom (st.chat_input)
  - Activity Log panel (persistent) + toasts for new events

#### Required helper signatures inside `streamlit_app.py`
```python
def init_session_state() -> None: ...
def render_sidebar() -> None: ...
def render_chat_main(orchestrator: OrchestratorFacade) -> None: ...
def render_activity_panel() -> None: ...
def emit_toast_once(ev: TraceEvent) -> None: ...
def main() -> None: ...
```

**Toast dedupe rule:**
- Create `st.session_state["seen_toast_ids"] = set()`
- If `ev.event_id` in set → do not toast again.

**Streaming/fade effect:**
- For each new TraceEvent appended during a turn, call `emit_toast_once(ev)` immediately.
- Persist the event into ActivityStream and show it in `render_activity_panel()`.

---

## UX details to implement (exactly)

### 1) Greeting turn should look like this:
User types: “HI”

Chat:
- user bubble: HI
- assistant bubble: “Hi! Ask me a question about your data (or type ‘help’ for examples).”

Activity toasts (fade):
- “Intent: greeting”
- “Decision: skip tools”

Persistent Activity panel shows same entries.

### 2) Real data question should show multi-step streaming:
Example: “Show me 10 rows from v_dlv_dep_prty_clr”

Toasts (fade, in order):
- “Intent: data question”
- “Decision: needs SQL” (and needs_search only if required)
- If search:
  - “Tool call: search metadata”
  - “Tool result: found 3 relevant tables”
- “SQL generated”
- “SQL executing…”
- “Rows returned: 10”

Chat should show:
- assistant message (explanation + next suggestions)
- SQL card
- Results grid

---

## Fixes you must make based on the code screenshots

### A) `main()` not defined / `st` not defined regressions
- Ensure `import streamlit as st` is present before calling `st.*`
- Ensure `def main(): ...` exists **above** any usage `main()` call
- Ensure `if __name__ == "__main__" or "streamlit" in sys.argv[0]: main()` is at the bottom (or simpler: just call `main()`)

### B) `st.set_page_config` placement
- Call `st.set_page_config(...)` near the start of `main()` **only once**.
- Do not call it at module import time *before* `import streamlit as st`.

### C) Chat history storage must be real (no `pass`)
In `app/ui/state.py` (or wherever you store session state), ensure these are implemented:

```python
def get_chat_history() -> list[ChatMessage]: ...
def append_chat_message(msg: ChatMessage) -> None: ...
def get_trace_events() -> list[TraceEvent]: ...
def append_trace_event(ev: TraceEvent) -> None: ...
```

No `pass` allowed in the final implementation.

---

## Tests (required)
Create tests (pytest) for `SearchDecider.decide(...)`:

- “hi” → intent greeting, needs_search False, needs_sql False
- “help” → intent help (or smalltalk), needs_search False, needs_sql False
- “show me 10 rows from table_x” → needs_sql True
- “what columns does table_x have” → needs_search True (sql optional depending on your design)

Tests must be deterministic; for LLM classification path, mock the LLM client.

---

## Acceptance checklist (must pass)
- [ ] Typing “hi” does NOT call metadata search or SQL.
- [ ] Activity log shows “Intent: greeting” then “Decision: skip tools” as toasts that fade.
- [ ] Chat always shows assistant response bubble.
- [ ] For real questions, tool calls happen only when needed.
- [ ] Activity log persistent panel retains all events; toasts show only once.
- [ ] No `pass` remains in state/chat functions.
- [ ] Unit tests for SearchDecider pass.

---

## Implementation guidance (do not skip)
1) Start by making `SearchDecider` deterministic for greetings/help/thanks.
2) Update `OrchestratorFacade.run_chat_turn` to obey `SearchDecision` (skip tools).
3) Ensure Streamlit UI:
   - appends user message
   - calls orchestrator once per input
   - appends assistant message
   - shows toasts for each TraceEvent
4) Ensure ActivityStream is stored in session_state so it survives reruns.
5) Add/adjust tests and run them.

---

## Commands to verify locally
Run these and paste outputs back if anything fails:

```bash
python -m compileall app/ui/streamlit_app.py app/ui/search_decider.py app/ui/orchestrator_facade.py
pytest -q
streamlit run app/ui/streamlit_app.py
```

---

## If you need more context
If anything is unclear, ask me for **one** missing file at a time (e.g., `app/ui/orchestrator_facade.py`, `app/ui/state.py`, `app/ui/search_decider.py`) and I will paste it. Do not guess large missing modules.
