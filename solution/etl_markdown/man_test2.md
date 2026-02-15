# Text2SQL Streamlit Chat — Fix “Hi triggers search” + Make Activity Log Stream/Fade

Use this prompt in **GitHub Copilot Chat** (in-repo) so Copilot makes **exact changes only** (no redesign).  
Goal: make the app behave like a **collaborative chat UI** where **AI Search** and **SQL execution** behave like **tools** that are invoked **only when needed**, and the **Activity Log streams step-by-step updates** (with a simple fade effect for older steps).

---

## What is broken now

1. When the user types **“hi”**, the app behaves like it’s a data/SQL question and triggers **metadata search + SQL**.
2. The **Activity Log** shows a batch list; you want it to behave like a **stream**: intent → (fade) → tool call → (fade) → tool result → (fade) → …
3. The architecture must be consistent with the “tools” concept:
   - **AI Search** and **SQL** are *tools*
   - The system decides whether to call them (deterministic for greetings/help/thanks)
   - For “smalltalk”, respond without search/sql

---

## Acceptance criteria (must pass)

### A) Greeting behavior
- Input: `hi` / `hello` / `hey` / `thanks` / `thank you` / `help`
- Output:
  - Assistant responds with a **friendly chat answer** (no metadata dump, no SQL)
  - Activity log shows something like:
    - `[intent] Intent detected: greeting (search=False, sql=False)`
    - `[respond] Responding without tools`
- **No AI Search call**
- **No SQL generation/execution**
- UI still shows chat transcript and activity stream.

### B) Data-question behavior
- Input: “show me 10 rows from v_dlv_dep_prty_clr” (or similar)
- Output:
  - Activity log streams steps in order: intent → search (optional) → prompt build → sql generated → validated → executed → result summary
  - Results are shown in the chat (assistant message) and optionally as grid below.
  - AI Search is only invoked if the decision says it’s needed.

### C) Activity log streaming + fade
- New steps appear live while the assistant is “thinking”.
- Older steps are still visible but **faded** (lower opacity) so the log feels like a stream.
- Keep it simple: CSS opacity + rerender; no complex JS.

### D) Strict structure rule
Implement the **exact class + method signatures** below.  
Do **not** invent new architecture. You may add small helper functions, but the public API must match.

---

## Required files and exact structures

### 1) `app/ui/models.py` (dataclasses + typing)
Ensure these exist (or match if they already exist). Do not rename.

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

Role = Literal["user", "assistant", "system"]

@dataclass(frozen=True)
class UIOptions:
    max_rows: int = 50
    execution_target: Literal["sqlite", "oracle"] = "sqlite"
    debug_enabled: bool = False

@dataclass
class ChatMessage:
    role: Role
    content: str
    ts_iso: str

TraceKind = Literal[
    "intent",
    "tool_call",
    "tool_result",
    "prompt_build",
    "sql_generated",
    "sql_sanitized",
    "sql_validated",
    "sql_executing",
    "sql_result",
    "respond",
    "error",
]

@dataclass
class TraceEvent:
    kind: TraceKind
    message: str
    ts_iso: str
    payload: Optional[dict[str, Any]] = None

@dataclass
class TurnResult:
    assistant_message: Optional[str] = None
    clarification_question: Optional[str] = None
    sql: Optional[str] = None
    df: Any = None  # typically pandas.DataFrame
    error_message: Optional[str] = None
    debug_details: Optional[str] = None
    trace_events: list[TraceEvent] = None
```

Notes:
- `TurnResult.trace_events` must default to an empty list safely (use `None` then set `[]` in `__post_init__`).
- Keep imports minimal; do not force pandas import at module import time if it causes issues.

---

### 2) `app/ui/search_decider.py` (deterministic tool gating)
Create/ensure these exact structures:

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from app.ui.models import ChatMessage

Intent = Literal["greeting", "help", "thanks", "data_query", "general_chat"]

@dataclass(frozen=True)
class SearchDecision:
    intent: Intent
    use_ai_search: bool
    use_sql: bool
    reason: str

class SearchDecider:
    def decide(self, user_text: str, history: list[ChatMessage]) -> SearchDecision:
        ...
```

#### Deterministic rules (must implement)
- If `user_text` matches greeting (case-insensitive): `hi`, `hello`, `hey`, `good morning`, `good afternoon`, `good evening`
  - `intent="greeting"`, `use_ai_search=False`, `use_sql=False`
- If it matches thanks: `thanks`, `thank you`, `thx`
  - `intent="thanks"`, `use_ai_search=False`, `use_sql=False`
- If it matches help: `help`, `?`, `what can you do`, `examples`
  - `intent="help"`, `use_ai_search=False`, `use_sql=False`
- Otherwise default:
  - `intent="data_query"` **if** it contains strong data hints like: `select`, `from`, `table`, `rows`, `columns`, `schema`, known table prefix patterns (`v_`, etc.)
  - Else: `intent="general_chat"` with `use_ai_search=False`, `use_sql=False`

Important:
- **Do NOT call AI Search for general chat**.
- AI Search should be used only when a query needs schema discovery / table mapping.

---

### 3) `app/ui/orchestrator_facade.py` (single entry point per turn)
Implement/ensure:

```python
from __future__ import annotations
from typing import Callable, Optional
from app.ui.models import UIOptions, ChatMessage, TurnResult, TraceEvent
from app.ui.search_decider import SearchDecider

TraceCallback = Callable[[TraceEvent], None]

class OrchestratorFacade:
    def run_chat_turn(
        self,
        user_text: str,
        history: list[ChatMessage],
        options: UIOptions,
        trace_cb: Optional[TraceCallback] = None,
    ) -> TurnResult:
        ...
```

#### Required behavior inside `run_chat_turn`
1. Call `SearchDecider().decide(user_text, history)` first.
2. Emit trace event:
   - kind=`"intent"`
   - message like: `Intent detected: {intent} (search={use_ai_search}, sql={use_sql})`
3. If `intent in {"greeting","help","thanks","general_chat"}`:
   - Emit trace event kind=`"respond"` message=`"Responding without tools"`
   - Return `TurnResult(assistant_message=...)` with a friendly response.
   - **Do not** call AI Search, SQL generation, SQL execution.
4. If `intent == "data_query"`:
   - Tool-like flow:
     - (optional) AI Search for metadata only when `use_ai_search=True`
     - prompt build
     - call LLM to produce SQL
     - sanitize/validate
     - execute SQL
     - send *result summary* back to LLM to produce final assistant answer
   - Emit trace events for each step using the `trace_cb`.

Important:
- Keep the existing back-end logic, but ensure it is **gated** by `SearchDecision`.

---

### 4) `app/ui/activity_stream.py` (live stream + fade rendering)
Implement/ensure:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from app.ui.models import TraceEvent

@dataclass
class ActivityStream:
    max_events: int = 50
    events: list[TraceEvent] = field(default_factory=list)

    def add(self, ev: TraceEvent) -> None:
        ...

    def clear(self) -> None:
        ...

    def render_html(self) -> str:
        ...
```

Rules:
- `add()` appends and trims to `max_events`.
- `render_html()` returns HTML with newest event normal opacity and older events “faded”.
- Do **not** include raw user data; only the trace event message.
- HTML can be used via `st.markdown(html, unsafe_allow_html=True)`.

Suggested fade approach:
- last event: `opacity:1`
- older: `opacity:0.35`
- add a small CSS transition.

---

### 5) `app/ui/state.py` (no `pass`, never return None)
Fix any leftover `pass` methods and ensure these exist and always return defaults:

```python
from __future__ import annotations
from typing import List
import streamlit as st
from app.ui.models import ChatMessage, TraceEvent, UIOptions
from app.ui.activity_stream import ActivityStream

DEFAULT_UI_OPTIONS = UIOptions()

def get_ui_options() -> UIOptions: ...
def set_ui_options(opts: UIOptions) -> None: ...

def get_chat_history() -> list[ChatMessage]: ...
def append_chat_message(msg: ChatMessage) -> None: ...
def clear_chat() -> None: ...

def get_activity_stream() -> ActivityStream: ...
def append_trace_event(ev: TraceEvent) -> None: ...
def clear_trace_events() -> None: ...
```

Implementation rules:
- `get_chat_history()` must initialize `st.session_state["messages"]` to `[]` if missing/None.
- `get_activity_stream()` must initialize a single `ActivityStream` object in session_state.
- Never return `None` for lists/objects.
- No UI rendering in this file.

---

### 6) `app/ui/streamlit_app.py` (chat-first rendering + live stream)
Required ordering rules:
1. `import streamlit as st` must be present before any `st.*` usage.
2. `st.set_page_config(...)` must be called **once** inside `main()` before rendering.
3. Ensure `bootstrap_project_root()` is called before `from app... import ...` (only if needed for imports).

Implement these functions:

```python
def bootstrap_project_root() -> None: ...
def inject_css() -> None: ...
def init_session_state() -> None: ...
def render_sidebar() -> None: ...
def render_chat_main(orchestrator) -> None: ...
def main() -> None: ...
```

#### Streaming behavior requirement
- Create a container for Activity Log (e.g., `activity_placeholder = st.empty()` or inside an expander).
- Pass a `trace_cb` into `orchestrator.run_chat_turn(...)` that:
  1) appends to session activity stream (`append_trace_event(ev)`), and
  2) re-renders the activity placeholder immediately with fade HTML (`activity_placeholder.markdown(...)`).

This produces “stream-like” updates as the script runs.

#### Chat transcript
- Use `st.chat_message(role)` for each message.
- Use `st.chat_input(...)` at bottom.
- When user submits, append user message, call orchestrator once, then append assistant message, then `st.rerun()`.

#### IMPORTANT UI fix: “Hi triggers search”
Once `SearchDecider` is wired, the transcript for “hi” must show only greeting response.

---

## Extra UX: “fade then replace” (simple and safe)
You asked: “intent shows first, then fades, then search shows, then fades…”

Implement as:
- Keep all events, but older ones are rendered with lower opacity.
- The newest event is highlighted (normal opacity).
- That visually gives the “fade” effect without timers or JS.

If you want “auto-hide” later, add a “Show last N events” slider in sidebar (optional).

---

## What to change right now (based on your current screenshots)

1. **Your app is calling AI search for “HI”** → this means `SearchDecider` is not used, or it defaults to data_query.
   - Implement deterministic greeting detection and wire it at the start of `run_chat_turn()`.
2. **Activity Log is appended but not streamed** → ensure trace callback updates a placeholder while the turn runs.
3. **Keep the tool-flow only for `intent="data_query"`**.

---

## Tests (must add)
Create `tests/test_search_decider.py`:

- `hi` → use_ai_search False, use_sql False
- `help` → False/False
- `thanks` → False/False
- `show me 10 rows from v_dlv_dep_prty_clr` → intent data_query and (likely) use_sql True

Run:
```bash
python -m compileall app/ui
pytest -q
```

---

## Verification commands (must include in your PR output)
```bash
python -m compileall app/ui
pytest -q
.venv/bin/streamlit run app/ui/streamlit_app.py
```

---

## Deliverables (Copilot must produce)
1. Updated files implementing the exact structures above.
2. Tests passing.
3. A short “What changed” summary:
   - greeting behavior fixed (no tools)
   - streamed activity log with fade
   - tool gating implemented via SearchDecider + OrchestratorFacade

---

## IMPORTANT: Do not redesign
- No new UI layout frameworks.
- No random refactor.
- Only implement what’s listed with the stated signatures and behavior.
