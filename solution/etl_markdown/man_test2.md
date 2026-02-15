# Fix Streamlit crash: `NameError: init_session_state is not defined` (and keep architecture consistent)

Use this prompt in **GitHub Copilot Chat / Codex** inside your repo.

---

## Context

- Streamlit crashes with: **`NameError: name 'init_session_state' is not defined`** in `app/ui/streamlit_app.py`.
- This happened after refactoring UI/state helpers into separate modules.
- **Pytest passes**, but Streamlit fails at runtime → this is a missing symbol / wiring issue (tests didn’t cover Streamlit import/run).

---

## Goal

1. `streamlit run app/ui/streamlit_app.py` works (no NameError).
2. `pytest -q` remains green.
3. Session-state helpers exist **exactly once** (single source of truth) and are imported correctly.
4. No architecture regressions: Streamlit UI calls state/helpers; state module owns session keys.

---

## Required public API (signatures must match)

These functions must exist and be callable (no `pass` placeholders):

### `app/ui/state.py`
- `def init_session_state() -> None:`
- `def get_chat_history() -> list["ChatMessage"]:`
- `def append_chat_message(msg: "ChatMessage") -> None:`
- `def clear_chat() -> None:`
- `def get_trace_events() -> list["TraceEvent"]:`
- `def append_trace_event(ev: "TraceEvent") -> None:`
- `def get_ui_options() -> "UIOptions":`

And constants:
- `DEFAULT_UI_OPTIONS: UIOptions`

### `app/ui/streamlit_app.py`
- `def main() -> None:`
- Must call, in order: `bootstrap_project_root()`, `inject_css()`, `init_session_state()`, `render_sidebar()`, create orchestrator, then `render_chat_main(orchestrator)`.

---

## What to change (do this exactly)

### Step 1 — Find the failing callsite
In `app/ui/streamlit_app.py`, locate where `init_session_state()` is called (likely inside `main()`).

- Confirm there is **no local definition** `def init_session_state(...):` in this file anymore.
- That’s why Python raises NameError.

### Step 2 — Make `init_session_state` come from the state module (recommended)
Make `app/ui/state.py` the **single source of truth** for session-state keys.

In `app/ui/streamlit_app.py`, add an import near the other state imports:

```python
from app.ui.state import init_session_state
```

(or import it alongside the other helpers you already import from `app.ui.state`)

Then keep the call as:

```python
init_session_state()
```

✅ This fixes the NameError while keeping your architecture clean.

> Alternative is `import app.ui.state as state` then call `state.init_session_state()`. Either is fine—pick one style and use it consistently.

### Step 3 — Ensure `init_session_state()` is actually implemented (idempotent)
In `app/ui/state.py`, implement:

```python
def init_session_state() -> None:
    """Initialize Streamlit session state keys if missing."""
```

**Rules:**
- Must be **idempotent** (safe to call multiple times).
- Must not wipe existing chat unless explicitly requested (e.g., via `clear_chat()`).
- Should initialize these keys if missing:
  - `"messages"`: list[ChatMessage]
  - `"activity"` (or `"trace_events"` depending on your chosen name): list[TraceEvent]
  - `"debug_enabled"`: bool
  - any state your ActivityStream needs (e.g., `"last_toast_idx"`)

Example structure (adjust key names to match your repo, but keep behavior):

```python
import streamlit as st

def init_session_state() -> None:
    if "messages" not in st.session_state or st.session_state["messages"] is None:
        st.session_state["messages"] = []
    if "trace_events" not in st.session_state or st.session_state["trace_events"] is None:
        st.session_state["trace_events"] = []
    if "debug_enabled" not in st.session_state:
        st.session_state["debug_enabled"] = False
```

### Step 4 — Ensure no circular imports
`app/ui/state.py` **must not import** `app/ui/streamlit_app.py` (directly or indirectly).

If you need types (`ChatMessage`, `TraceEvent`, `UIOptions`), import them from `app/ui/models.py`:

```python
from app.ui.models import ChatMessage, TraceEvent, UIOptions
```

If runtime import causes cycles, use:

```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.ui.models import ChatMessage, TraceEvent, UIOptions
```

But in most cases, importing models into state is fine.

### Step 5 — (Optional but strongly recommended) Add a Streamlit smoke test
Your tests passed but Streamlit failed. Add a small test to prevent this regression.

Create `app/ui/test_streamlit_import.py`:

```python
def test_streamlit_app_imports():
    import app.ui.streamlit_app  # noqa: F401
```

This doesn’t run Streamlit UI, but it catches import-time NameErrors and missing symbols.

---

## Verification checklist (must run these)

1. **Unit tests**
```bash
pytest -q
```

2. **Run Streamlit**
```bash
streamlit run app/ui/streamlit_app.py
```

3. **Sanity check in browser**
- Page loads
- “Text2SQL Chat” header renders
- Typing `hi` adds a user message and assistant reply (even if it’s a basic greeting)

---

## Deliverables you must produce

1. A git-style patch or commit modifying:
   - `app/ui/streamlit_app.py` (import fix)
   - `app/ui/state.py` (implement `init_session_state`)
   - (optional) `app/ui/test_streamlit_import.py` (smoke test)
2. A short “What changed / Why” summary.
3. Paste the final versions of any modified functions (especially `init_session_state`) in the chat so I can verify signatures.

---

## Hard constraints (do NOT violate)

- Do **not** rename existing public functions that other files already import.
- Do **not** change function signatures listed above.
- Do **not** remove the existing SearchDecider / OrchestratorFacade design (if present).
- Keep behavior backward compatible: don’t wipe existing session messages on load.

---

## If you hit another NameError after this
Repeat the same pattern:
- Find missing symbol → decide single source of truth → import it explicitly → add a smoke test that imports the file.

