# Text2SQL Streamlit UI — Fix “chat input does nothing / messages not showing” + Validate Architecture

## Context / Symptom
- The Streamlit page loads and shows **Text2SQL Chat** and **Activity Log**, but:
  - The initial greeting message may not appear.
  - When the user types **“hi”** (or any message), **nothing shows in the chat transcript**.
  - Backend logs show the pipeline is running (LLM SQL extraction, execution, etc.), but UI doesn’t reflect it.

## Most likely root cause
This is a common Streamlit chat pattern issue:

1. Your code renders the chat transcript **before** reading `st.chat_input()`.
2. When the user submits text, you **append messages to `st.session_state` after the transcript has already been rendered**.
3. Streamlit does not automatically re-render earlier blocks inside the same run unless you:
   - render the new message immediately in the same run **and/or**
   - call `st.rerun()` after updating the state.

Result: the user submits a message and sees nothing until a later rerun (or never, if state functions return copies / not persisted).

---

## Required architecture (do NOT redesign — implement exactly these structures)

### `app/ui/models.py`
```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Role = Literal["user", "assistant", "system"]

@dataclass
class ChatMessage:
    role: Role
    content: str
    ts_iso: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)

@dataclass
class TraceEvent:
    ts_iso: str
    stage: str                 # e.g. "decide_search", "fetch_metadata", "generate_sql", "execute_sql"
    message: str               # human friendly
    payload: dict[str, Any] = field(default_factory=dict)
```

### `app/ui/state.py`
All state functions MUST be safe (never return None) and must always persist into `st.session_state`.

```python
from __future__ import annotations
from typing import List
import streamlit as st
from app.ui.models import ChatMessage, TraceEvent

DEFAULT_DEBUG_ENABLED = False

def init_session_state() -> None:
    if "messages" not in st.session_state or st.session_state["messages"] is None:
        st.session_state["messages"] = []
    if "trace_events" not in st.session_state or st.session_state["trace_events"] is None:
        st.session_state["trace_events"] = []
    if "debug_enabled" not in st.session_state or st.session_state["debug_enabled"] is None:
        st.session_state["debug_enabled"] = DEFAULT_DEBUG_ENABLED
    if "last_result" not in st.session_state:
        st.session_state["last_result"] = None

def get_chat_history() -> List[ChatMessage]:
    init_session_state()
    return st.session_state["messages"]

def append_chat_message(msg: ChatMessage) -> None:
    init_session_state()
    st.session_state["messages"].append(msg)

def clear_chat() -> None:
    init_session_state()
    st.session_state["messages"] = []

def get_trace_events() -> List[TraceEvent]:
    init_session_state()
    return st.session_state["trace_events"]

def append_trace_event(ev: TraceEvent) -> None:
    init_session_state()
    st.session_state["trace_events"].append(ev)

def clear_trace() -> None:
    init_session_state()
    st.session_state["trace_events"] = []
```

### `app/ui/orchestrator_client.py` (interface expectation)
Your UI will call ONE method with this signature. Implementers can adapt internally but MUST expose it.

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

import pandas as pd
from app.ui.models import ChatMessage, TraceEvent

@dataclass
class UIOptions:
    max_rows: int
    execution_target: Literal["sqlite", "oracle"]
    debug_enabled: bool

@dataclass
class ChatTurnResult:
    assistant_message: Optional[str] = None
    clarification_question: Optional[str] = None
    sql: Optional[str] = None
    df: Optional[pd.DataFrame] = None
    error_message: Optional[str] = None
    debug_details: dict[str, Any] = None

class OrchestratorClient:
    def run_turn(
        self,
        user_text: str,
        history: list[ChatMessage],
        options: UIOptions,
        trace_cb: Optional[Callable[[TraceEvent], None]] = None,
    ) -> ChatTurnResult:
        ...
```

---

## REQUIRED UI behavior
1. The **main area must always show a chat transcript**:
   - At minimum, an assistant greeting if chat is empty.
2. When the user submits text:
   - The **user message must appear immediately**.
   - The app must show an assistant response (even if response is “Search not needed, here’s why…”).
3. An **Activity Log** panel must always be visible and update during processing:
   - Example stages: deciding search, fetching AI Search, reviewing schema, generating SQL, executing SQL.
4. The **dataset/results** must come back to the assistant and be shown **in the chat flow** (not just a separate silent table).

---

## Fix to implement (Streamlit chat rendering pattern)

### File: `app/ui/streamlit_app.py`
Implement the chat like this:

#### A) Always render history first
- Ensure the greeting exists in session state BEFORE rendering.

#### B) Read `st.chat_input(...)`
- When user submits:
  - Render the user bubble immediately with `st.chat_message("user")`
  - Call orchestrator
  - Render assistant bubble immediately with `st.chat_message("assistant")`
  - Persist both messages into session_state
  - Call `st.rerun()` at the end to ensure the transcript shows consistently

### Reference implementation (what Copilot should create)
> Keep your existing helpers, but the logic MUST follow this order.

```python
import datetime
import streamlit as st

from app.ui.state import (
    init_session_state,
    get_chat_history,
    append_chat_message,
    get_trace_events,
    append_trace_event,
)
from app.ui.models import ChatMessage, TraceEvent
from app.ui.orchestrator_client import UIOptions, OrchestratorClient

def render_chat_main(orchestrator: OrchestratorClient) -> None:
    init_session_state()

    st.title("Text2SQL Chat")

    # 1) Ensure greeting exists BEFORE rendering transcript
    messages = get_chat_history()
    if not messages:
        append_chat_message(ChatMessage(
            role="assistant",
            content="Hi! Ask me a question about your data (or say 'help' to see examples).",
            ts_iso=datetime.datetime.utcnow().isoformat()
        ))
        messages = get_chat_history()

    # 2) Render transcript
    for msg in messages:
        with st.chat_message(msg.role):
            st.markdown(msg.content)

    # 3) Input
    user_text = st.chat_input("Type your question and press Enter…")
    if not user_text:
        return

    # 4) Render user message IMMEDIATELY in same run
    ts = datetime.datetime.utcnow().isoformat()
    with st.chat_message("user"):
        st.markdown(user_text)
    append_chat_message(ChatMessage(role="user", content=user_text, ts_iso=ts))

    # 5) Activity log placeholder (updates while running)
    activity_placeholder = st.empty()

    def trace_cb(ev: TraceEvent) -> None:
        append_trace_event(ev)
        # Re-render the activity log live
        events = get_trace_events()
        with activity_placeholder.container():
            st.subheader("Activity Log")
            for e in events[-50:]:
                st.write(f"• [{e.stage}] {e.message}")

    # 6) Orchestrate + render assistant message IMMEDIATELY
    with st.chat_message("assistant"):
        with st.spinner("Assistant is thinking..."):
            options = UIOptions(max_rows=50, execution_target="sqlite", debug_enabled=st.session_state.get("debug_enabled", False))
            history = get_chat_history()

            # IMPORTANT: do not pass a COPY unless orchestrator expects it.
            # If you pass a copy, the orchestrator will not see appended messages.
            result = orchestrator.run_turn(user_text=user_text, history=history, options=options, trace_cb=trace_cb)

        # Render assistant text
        if result.error_message:
            st.error(result.error_message)
            assistant_text = f"Error: {result.error_message}"
        elif result.clarification_question:
            st.markdown(result.clarification_question)
            assistant_text = result.clarification_question
        else:
            assistant_text = result.assistant_message or "(No assistant message returned)"
            st.markdown(assistant_text)

        # Render SQL + results as part of assistant message
        if result.sql:
            st.code(result.sql, language="sql")
        if result.df is not None:
            st.dataframe(result.df)

    # Persist assistant message at the end
    append_chat_message(ChatMessage(role="assistant", content=assistant_text, ts_iso=datetime.datetime.utcnow().isoformat()))

    # 7) Force re-render so transcript is consistent
    st.rerun()
```

---

## Critical correctness checks (Copilot MUST verify)

### 1) No duplicate `st.set_page_config()`
- `st.set_page_config()` must be called **once** near the top-level execution path.
- If you call it twice, Streamlit will throw warnings/errors in some versions.

### 2) Bootstrap `sys.path` BEFORE any `from app...` imports
If you must modify `sys.path` for Streamlit, do it at the top before importing your own packages:

```python
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
```

Then import `streamlit` and your `app.*` modules.

### 3) State functions must NOT return None
- `get_chat_history()` must always return a list (possibly empty).
- `append_chat_message()` must always append to the same list stored in `st.session_state`.

### 4) “hi” should not silently become SQL (optional but recommended)
If your product requirement says: “Sometimes search/SQL is not needed,” then implement a simple decision step:

- If input is small talk (“hi”, “hello”), respond conversationally and **do not** run SQL.
- Log a trace event: `[decide_search] Search not needed for greeting/small talk.`

Where to put this:
- Inside orchestrator `run_turn()` (preferred).
- Or in UI before calling orchestrator (acceptable, but keep logic centralized if possible).

### 5) Activity log must update during processing
- Use an `st.empty()` placeholder and update it from `trace_cb`.
- Keep it to last N events (e.g., 50) to avoid slow rendering.

---

## Verification steps (commands)
From repo root:

1) Syntax check:
```bash
.venv/bin/python -m compileall app/ui/streamlit_app.py app/ui/state.py app/ui/models.py
```

2) Run Streamlit (always use venv binary):
```bash
.venv/bin/streamlit run app/ui/streamlit_app.py
```

3) In the browser:
- You should immediately see an assistant greeting.
- Type `hi`
  - You must see a **user bubble** with `hi`.
  - You must see an **assistant bubble** replying.
  - The activity log should show at least one event (even if “search not needed”).

---

## Deliverables Copilot must produce
1. Updated `app/ui/streamlit_app.py` implementing the fixed chat rendering pattern (immediate render + `st.rerun()`).
2. Verified `app/ui/state.py` returns lists, never None, and persists state correctly.
3. Verified `app/ui/models.py` includes `ChatMessage` and `TraceEvent` and matches signatures.
4. (Optional) Add a minimal unit test for `state.py` state initialization (if your repo already has a test harness).

---

## If anything is unclear / missing
Copilot must **not guess** filenames or move modules around.
If imports don’t match the repo, it must:
1) Search the repo for the actual module paths (`app/ui/state.py`, `app/ui/models.py`, etc.)
2) Update imports to match the existing structure while keeping the exact function/class signatures specified above.
