# Text2SQL Streamlit UI — Fix `NameError: main is not defined` + Enforce Chat-First Architecture (Copilot Prompt)

> **Copy/paste this entire prompt into GitHub Copilot Chat (in your repo root).**  
> Goal: **fix the current runtime errors** and **make sure the implementation matches the required chat-first design** (chat transcript in main area, streaming activity log, deterministic “use search?” decision, results returned to the assistant message).

---

## 0) Context (what you must assume)

- Repo has a Streamlit entrypoint: `app/ui/streamlit_app.py`
- The app is **chat-first**:
  - User asks a question in chat
  - Assistant decides if **AI Search** is needed (or not) and logs steps
  - If needed: fetch metadata / schema info (via AI Search or equivalent)
  - Generate SQL and execute query
  - **Return SQL + query results back into the assistant chat response**
  - Show a **streaming activity log** (not hidden chain-of-thought; just step logs like “Deciding search…”, “Fetching metadata…”, “Generating SQL…”, “Executing…”)

---

## 1) Immediate bug to fix (observed)

### A) Current error
`NameError: name 'main' is not defined`  
Happens because `main()` is being called at module import time **before** `def main()` exists, or because `main` is not defined at module scope (e.g., nested/indented incorrectly), or there is a stray `main()` call above its definition.

### B) Previously seen errors (must not regress)
- `NameError: name 'st' is not defined` (Streamlit used before `import streamlit as st`)
- `ModuleNotFoundError` import path issues (`app` not found) because project root not in `sys.path`

---

## 2) Hard requirements (do not “redesign”, just implement exactly)

### UI must always show (main area)
1. Title/header (TD-themed is OK; minimal)
2. Chat transcript (show at least a greeting if empty)
3. Chat input at the bottom (`st.chat_input`)
4. Activity log panel/expander that updates while the turn runs

### “Process of thought” requirement
- **Do NOT show hidden chain-of-thought.**
- Instead, implement an **Activity Log** stream of deterministic steps:
  - `Deciding whether AI search is needed...`
  - `Using AI search: YES/NO (reason: ...)`
  - `Fetching metadata from index ...`
  - `Reviewing table structure ...`
  - `Generating SQL ...`
  - `Executing SQL ...`
  - `Formatting results ...`

### Architecture requirement
You MUST keep these **exact module/class/function signatures** (create or adjust files as needed):

#### `app/ui/models.py`
```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal, Optional

@dataclass
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str
    ts_iso: Optional[str] = None

@dataclass
class TraceEvent:
    ts_iso: str
    stage: str                 # e.g. "search_decision", "search_fetch", "sql_gen", "sql_exec"
    message: str               # human readable log line
    data: Optional[dict[str, Any]] = None

@dataclass
class UIOptions:
    max_rows: int = 50
    execution_target: Literal["sqlite", "oracle"] = "oracle"  # placeholder if needed
    debug_enabled: bool = False

@dataclass
class TurnResult:
    assistant_message: Optional[str] = None
    clarification_question: Optional[str] = None
    sql: Optional[str] = None
    df: Any = None                       # keep Any to avoid hard pandas dep here
    error_message: Optional[str] = None
    debug_details: Optional[dict[str, Any]] = None
```

#### `app/ui/state.py`
```python
from __future__ import annotations
from typing import List
from app.ui.models import ChatMessage, TraceEvent, UIOptions

DEFAULT_UI_OPTIONS = UIOptions()

def init_session_state() -> None: ...
def get_chat_history() -> List[ChatMessage]: ...
def append_chat_message(msg: ChatMessage) -> None: ...
def clear_chat() -> None: ...

def get_trace_events() -> List[TraceEvent]: ...
def append_trace_event(ev: TraceEvent) -> None: ...
def clear_trace() -> None: ...

def get_ui_options() -> UIOptions: ...
def set_ui_options(opts: UIOptions) -> None: ...
```

#### `app/ui/orchestrator_client.py`
```python
from __future__ import annotations
from typing import Callable, Optional, List
from app.ui.models import ChatMessage, TurnResult, UIOptions, TraceEvent

TraceCallback = Callable[[TraceEvent], None]

class OrchestratorClient:
    def run_turn(
        self,
        user_text: str,
        history: List[ChatMessage],
        options: UIOptions,
        trace_cb: Optional[TraceCallback] = None,
    ) -> TurnResult: ...
```

#### `app/core/search_decider.py`
```python
from __future__ import annotations
from dataclasses import dataclass
from typing import List
from app.ui.models import ChatMessage

@dataclass
class SearchDecision:
    use_search: bool
    reason: str
    query: str | None = None

def decide_use_search(user_text: str, history: List[ChatMessage]) -> SearchDecision: ...
```

#### `app/core/orchestrator_facade.py`
```python
from __future__ import annotations
from typing import Callable, Optional, List
from app.ui.models import ChatMessage, TurnResult, UIOptions, TraceEvent
from app.ui.orchestrator_client import TraceCallback

def run_chat_turn(
    user_text: str,
    history: List[ChatMessage],
    options: UIOptions,
    trace_cb: Optional[TraceCallback] = None,
) -> TurnResult: ...
```

#### UI components (minimal but required)
- `app/ui/components/chat.py` → `render_header() -> None`
- `app/ui/components/trace.py` → `render_trace_panel(events, enabled: bool) -> None`
- `app/ui/components/results.py` → 
  - `render_sql_card(sql: str | None) -> None`
  - `render_results_grid(df) -> None`
  - `render_error_card(msg: str, debug: dict | None, debug_enabled: bool) -> None`
  - `render_explanation(text: str | None) -> None`

---

## 3) Streamlit entrypoint contract (MUST DO EXACTLY)

### File: `app/ui/streamlit_app.py`
Implement this exact top-level flow:

#### Required functions
```python
from __future__ import annotations
from pathlib import Path

def bootstrap_project_root() -> Path: ...
def inject_css() -> None: ...
def init_session_state() -> None: ...
def render_sidebar() -> None: ...
def render_chat_main(orchestrator) -> None: ...
def main() -> None: ...
```

#### **Non-negotiable ordering**
1. `bootstrap_project_root()` must run before any `import app.*`
2. `import streamlit as st` must happen before any `st.*`
3. `main()` must be defined **before** it is called
4. Only call `main()` inside the bottom guard:

```python
if __name__ == "__main__":
    main()
```

✅ **Remove** any stray `main()` calls above the definition.  
✅ **Remove** any weird guard like `or "streamlit" in sys.argv[0]` (it can cause unexpected execution ordering).

---

## 4) Exact fix you must implement now (to eliminate `main` / ordering bugs)

### Step 1 — Make `streamlit_app.py` safe and deterministic
- At the very top:
  - `import sys`
  - `from pathlib import Path`
- Define and immediately call `bootstrap_project_root()` **before** importing any `app.*` modules.
- Then `import streamlit as st`
- Then define all functions (`inject_css`, `render_sidebar`, `render_chat_main`, `main`)
- Only then call `main()` in the bottom guard.

### Step 2 — Ensure `set_page_config` is correct
- Call `st.set_page_config(...)` **once**, at the beginning of `main()`.
- Do not call `st.set_page_config` at module import time.

### Step 3 — Ensure chat is never blank
In `render_chat_main(...)`:
- Always render transcript:
  - If history is empty, append a greeting assistant message
- Always render `st.chat_input(...)`
- When user submits input:
  - append the user message
  - run orchestrator
  - append assistant/clarification message
  - render SQL + results below the assistant message (cards/grid)
  - render activity log panel (always visible or in expander)

### Step 4 — Stream activity log while running
Inside the “user submitted input” branch:
- Create a placeholder: `trace_placeholder = st.empty()`
- Define a `trace_cb(ev)` that:
  - appends to session state
  - re-renders the trace panel into the placeholder **during execution**
- Pass `trace_cb` into `orchestrator.run_turn(...)`

---

## 5) Orchestrator behavior (minimum acceptable)

Implement `app/core/orchestrator_facade.run_chat_turn(...)` so the turn does:

1. Emit TraceEvent: “Deciding whether AI search is needed”
2. Call `decide_use_search(...)`
3. Emit TraceEvent: “Using AI search: YES/NO (reason...)”
4. If YES:
   - Fetch metadata (stub allowed, but must be cleanly structured and logged)
5. Generate SQL (stub allowed if your engine already exists; otherwise call your existing pipeline)
6. Execute SQL and return dataframe
7. Compose `assistant_message` summarizing what happened and key findings
8. Return `TurnResult(sql=..., df=..., assistant_message=...)`
9. On exceptions:
   - return `TurnResult(error_message=..., debug_details=...)`
   - also log a TraceEvent with stage `"error"`

---

## 6) Verification checklist (you MUST run + report)

### Commands
```bash
# 1) Syntax check
python -m compileall app/ui/streamlit_app.py

# 2) Import check (should not execute main at import time)
python -c "import app.ui.streamlit_app as m; print('import ok')"

# 3) Start app
streamlit run app/ui/streamlit_app.py
```

### Expected behavior
- No `NameError: main is not defined`
- Main page shows:
  - Title
  - Chat transcript (greeting)
  - Chat input
  - Activity Log panel/expander
- On a question:
  - Activity log updates while running
  - Assistant responds in chat
  - SQL and results appear under assistant response

---

## 7) Unit tests you must add (small but mandatory)

Create: `tests/test_search_decider.py`
- Tests for `decide_use_search`:
  - trivial greeting → `use_search=False`
  - table/schema question → `use_search=True` (or your chosen heuristic) with reason
  - make decision deterministic

Run:
```bash
pytest -q
```

---

## 8) Deliverables (do not skip)

1. Updated `app/ui/streamlit_app.py` fixing ordering + main call
2. Ensure all required modules exist with the exact signatures above
3. `tests/test_search_decider.py` passing
4. A short “What changed” summary in the PR/commit message

---

## 9) If anything is missing
If you cannot implement because a referenced module does not exist, you MUST:
- create it with the required signature, minimal working implementation, and TODO markers
- do NOT leave imports broken
- do NOT redesign the UI

---

### Start now
Implement the fixes, run the verification commands, and ensure the UI shows chat in the main area.
