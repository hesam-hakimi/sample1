# Text2SQL UI — Fix `get_trace_events` NameError + Validate Trace/Activity Architecture

This guide fixes the current Streamlit crash:

> `NameError: name 'get_trace_events' is not defined`

…and ensures the **trace/activity pipeline** is implemented consistently across files (UI → state → activity stream), with **explicit function/class signatures** so Copilot can’t “guess” wrong symbols.

---

## 0) What’s happening (root cause)

`app/ui/streamlit_app.py` calls `get_trace_events()` (seen in the traceback), but:

- the function is **not imported** in `streamlit_app.py`, and/or
- the function is **not implemented** (or not exported) in `app/ui/state.py`.

So Streamlit reaches runtime and fails immediately during render.

---

## 1) Target architecture (must match across files)

### 1.1 Canonical models (already in your plan)
In `app/ui/models.py` (or wherever you placed them), these must exist:

```python
from dataclasses import dataclass
from typing import Any, Literal, Optional

@dataclass
class UIOptions:
    max_rows: int = 50
    execution_target: str = "sqlite"
    debug_enabled: bool = False

@dataclass
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str
    ts_iso: Optional[str] = None

@dataclass
class TraceEvent:
    event_type: str           # e.g. "intent", "tool_call", "tool_result", ...
    message: str              # human-friendly text
    ts_iso: Optional[str] = None
    level: str = "info"       # "info" | "warning" | "error"
    data: Optional[Any] = None

@dataclass
class TurnResult:
    assistant_message: Optional[str] = None
    clarification_question: Optional[str] = None
    sql: Optional[str] = None
    df: Any = None
    error_message: Optional[str] = None
    debug_details: Optional[str] = None
```

If any of these classes have different names/fields in your repo, **standardize now** (or update all imports consistently).

---

## 2) Fix: implement + import `get_trace_events`

### 2.1 Required session-state keys
Your Streamlit session must keep these keys (minimum):

- `messages: list[ChatMessage]`
- `trace_events: list[TraceEvent]`
- `debug_enabled: bool`
- (optional) `ui_options: UIOptions`

You already fixed `init_session_state()`—now we make sure trace functions are present and used everywhere.

---

## 3) Update `app/ui/state.py`

### 3.1 Add/confirm these signatures (DO NOT CHANGE NAMES)

**`app/ui/state.py` must export:**

```python
from __future__ import annotations

from typing import List
import streamlit as st

from app.ui.models import ChatMessage, TraceEvent, UIOptions

DEFAULT_UI_OPTIONS = UIOptions(
    max_rows=50,
    execution_target="sqlite",
    debug_enabled=False,
)

def init_session_state() -> None:
    """Initialize Streamlit session state keys if missing."""
    if "messages" not in st.session_state or st.session_state["messages"] is None:
        st.session_state["messages"] = []
    if "trace_events" not in st.session_state or st.session_state["trace_events"] is None:
        st.session_state["trace_events"] = []
    if "debug_enabled" not in st.session_state:
        st.session_state["debug_enabled"] = False

def get_chat_history() -> List[ChatMessage]:
    """Return chat history from session state. Never returns None."""
    init_session_state()
    return st.session_state["messages"]

def append_chat_message(msg: ChatMessage) -> None:
    """Append a message to chat history in session state."""
    init_session_state()
    st.session_state["messages"].append(msg)

def clear_chat() -> None:
    """Clear chat history (and optionally trace)."""
    init_session_state()
    st.session_state["messages"] = []
    # keep trace if you want; otherwise clear too:
    # st.session_state["trace_events"] = []

def get_trace_events() -> List[TraceEvent]:
    """Return trace events from session state. Never returns None."""
    init_session_state()
    return st.session_state["trace_events"]

def append_trace_event(ev: TraceEvent) -> None:
    """Append a trace event to session state."""
    init_session_state()
    st.session_state["trace_events"].append(ev)

def clear_trace_events() -> None:
    """Clear trace events."""
    init_session_state()
    st.session_state["trace_events"] = []

def get_ui_options() -> UIOptions:
    """
    Return UIOptions derived from session_state and env.
    Must sanitize invalid session_state values.
    """
    init_session_state()
    # NOTE: keep your existing sanitize logic that made tests pass.
    opts = DEFAULT_UI_OPTIONS

    max_rows = st.session_state.get("max_rows", opts.max_rows)
    if not isinstance(max_rows, int) or max_rows <= 0:
        max_rows = opts.max_rows

    execution_target = st.session_state.get("execution_target", opts.execution_target)
    if not isinstance(execution_target, str) or not execution_target:
        execution_target = opts.execution_target

    debug_enabled = st.session_state.get("debug_enabled", opts.debug_enabled)
    if not isinstance(debug_enabled, bool):
        debug_enabled = opts.debug_enabled

    return UIOptions(
        max_rows=max_rows,
        execution_target=execution_target,
        debug_enabled=debug_enabled,
    )
```

**Important**
- `get_trace_events()` and `append_trace_event()` must **always** call `init_session_state()` so they never return `None`.
- Keep your stricter test-compliant `get_ui_options()` logic (above is a safe example).

---

## 4) Update `app/ui/streamlit_app.py` (fix the NameError)

### 4.1 Ensure these imports exist
At the top of `app/ui/streamlit_app.py` (inside your current import section), import the missing symbol(s):

```python
from app.ui.state import (
    init_session_state,
    get_chat_history,
    append_chat_message,
    get_trace_events,         # ✅ REQUIRED
    append_trace_event,       # ✅ REQUIRED (if used by trace_cb)
    get_ui_options,
    clear_chat,
    DEFAULT_UI_OPTIONS,
)
```

### 4.2 Ensure render uses the function (not a missing local name)
Where you currently do:

```python
events = get_trace_events()
```

that will now resolve correctly.

---

## 5) Trace streaming behavior (fade + step-by-step)

You want the activity panel to behave like a stream:

- show “Intent…”
- then fade it
- show “Searching…”
- fade it
- etc.

Streamlit can’t “fade” existing rendered text unless you **re-render the panel** with different opacity. The simplest stable approach:

### 5.1 Store event timestamps + render with “age-based opacity”
In your trace renderer (e.g. `app/ui/components/trace.py`), apply opacity based on recency:

- newest event = 1.0 opacity
- older events gradually reduced (0.6, 0.4, 0.2)

Example renderer:

```python
import streamlit as st
from app.ui.models import TraceEvent

def render_trace_panel(events: list[TraceEvent], enabled: bool) -> None:
    if not enabled:
        return

    st.markdown("### Activity Log")
    n = len(events)
    for i, ev in enumerate(events):
        age = (n - 1) - i
        opacity = max(0.2, 1.0 - 0.15 * age)
        st.markdown(
            f"<div style='opacity:{opacity}; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;'>"
            f"• [{ev.event_type}] {ev.message}"
            f"</div>",
            unsafe_allow_html=True,
        )
```

This meets your “fade older items” requirement without timers.

### 5.2 If you want true “live streaming” while the model runs
Use a placeholder and update it inside the callback:

- create `panel = st.empty()`
- each time a trace event arrives, re-render the list into the placeholder

You must keep all events in `st.session_state["trace_events"]`.

---

## 6) Tool-gating for greetings (“hi” should not call AI Search)

You already added a `SearchDecider`. The rule must be deterministic:

- greetings/help/thanks → **no tool call**, respond directly
- only if user asks about data or schema → run tool chain (AI Search + SQL)

In orchestrator pseudocode:

```python
decision = search_decider.decide(user_text, history)

if decision.kind == "NO_TOOLS":
    return TurnResult(assistant_message=decision.reply)
```

Also append trace:

```python
append_trace_event(TraceEvent(event_type="intent", message=f"Intent detected: {decision.intent_label}"))
```

---

## 7) Add a “smoke test” to prevent these NameErrors

Create: `app/ui/test_streamlit_import.py`

```python
def test_streamlit_app_imports():
    import app.ui.streamlit_app  # noqa: F401
```

This catches missing imports like `get_trace_events` before runtime.

---

## 8) Verification checklist (must pass)

Run:

```bash
.venv/bin/pytest -q
.venv/bin/streamlit run app/ui/streamlit_app.py
```

Expected:
- ✅ Pytest passes
- ✅ Streamlit loads without NameError
- ✅ “hi” produces a friendly assistant response with **no** tool call
- ✅ Activity log shows events in order; older events appear faded (if enabled)

---

## 9) If you still see `NameError` after this

Search for the symbol:

```bash
grep -R "get_trace_events" -n app/ui
```

Common causes:
- typo like `get_trace_event` vs `get_trace_events`
- import shadowed by another local function
- circular import (fix by importing only inside functions that need it)

---

## Summary of the minimal fix

1. Implement `get_trace_events()` (and related trace helpers) in `app/ui/state.py`.
2. Import `get_trace_events` in `app/ui/streamlit_app.py`.
3. Add an import smoke test so this never happens again.

