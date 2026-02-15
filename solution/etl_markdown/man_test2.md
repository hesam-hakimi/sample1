# Copilot Prompt — Step: Frontend Streamlit UI (TD theme + event stream)

You are working in repo **text2sql_v2**. Backend now supports **structured event logs** during execution (planner → ai_search → prompt → llm → sql_sanitize → sql_execute → fallback / clarify / error). The CLI smoke tests pass.

**Goal (this step):** Upgrade the Streamlit UI to:
1) look modern with **TD-like white + green** styling, clean cards, optional TD logo  
2) support a **chat experience** (user asks, assistant answers)  
3) show an **Activity Log** panel that **streams live events** (e.g., “planning… calling AI search… generating SQL… executing…”)  
4) allow **debug mode**: Activity Log visible only when debug is ON  
5) support **keyboard shortcut** for submit (Enter) and allow newline with Shift+Enter  
6) fix the issue where UI shows **“(No assistant message returned)”** after user says “hi” (must always return a friendly assistant response)

---

## Constraints
- Keep Streamlit (no heavy UI frameworks).
- Add dependencies only if absolutely necessary (prefer stdlib + existing deps).
- No secrets in code. Keep using `.env` via existing config loader.
- Do not redesign backend router/orchestrator—UI should be a thin consumer.

---

## A) UI layout + styling (TD theme)
Update: `app/ui/streamlit_app.py`

**Header**
- Title: “Text2SQL Chat”
- Optional logo: if `app/ui/assets/td_logo.png` exists, show it; otherwise skip.

**Theme**
- White background, TD-green accent (use a single constant like `TD_GREEN = "#00A94F"` or similar).
- Use `st.markdown(<style>, unsafe_allow_html=True)` + CSS for:
  - chat bubbles (user vs assistant)
  - clean cards (border, subtle shadow, rounded corners)
  - activity log lines (small monospace + muted)

---

## B) Chat state + message rendering
Keep history in `st.session_state`:
- `messages`: list of `{"role": "user"|"assistant", "content": str}`
- `activity`: list of log lines (strings) OR event objects (then format at render time)

Create helper functions (these signatures must exist for future edits):

```python
def init_state() -> None: ...
def render_header() -> None: ...
def render_messages(messages: list[dict]) -> None: ...
def render_activity_log(activity: list[str], enabled: bool) -> None: ...
def append_message(role: str, content: str) -> None: ...
```

**Fix “No assistant message returned”**
- Every user input MUST result in an assistant message.
- If backend returns empty/None, show fallback:
  “Hi! Ask me a question about your data, or type ‘help’ for examples.”

---

## C) Streaming Activity Log from backend events
Wire Streamlit to show events as they arrive.

Implement:

```python
def format_event_line(event: object) -> str:
    """Convert backend event objects/dicts/strings into one log line."""

def run_chat_turn(user_text: str, debug: bool) -> None:
    """Runs one chat turn: streams events to Activity Log and appends final assistant message."""
```

**Event format compatibility**
Backend may emit:
- dataclass objects (with `.type`/`.message` or similar)
- dicts (keys like `type`, `message`)
- strings

Formatter must handle all 3 safely (never crash).

**Streaming**
- Use `st.empty()` placeholders to incrementally update the Activity Log panel while the backend runs.

Recommended log line format:
- `[{type}] {message}`

---

## D) Input UX + keyboard shortcut
- Default: `st.chat_input()` (Enter submits).
- If multiline needed: add a toggle to switch to `st.text_area()` + “Send”.
- Debug toggle in sidebar: Activity Log hidden when debug OFF.

---

## Backend integration (thin)
UI should call ONE backend entrypoint used by CLI (preferred).
If a tiny adapter is needed, add:

File: `app/ui/ui_backend_adapter.py`

```python
from collections.abc import Iterator
from typing import Any

def run_request_stream(user_text: str) -> Iterator[Any]:
    """Yield events during execution; last yield may be the final result event."""

def extract_final_assistant_text(events: list[Any]) -> str:
    """Return the assistant text from accumulated events/results."""
```

Keep adapter minimal (call existing orchestrator/router).

---

## Tests (required before manual UI testing)
Create: `tests/test_ui_event_formatting.py`

Test cases:
- `format_event_line()` handles:
  - dict event with `type` + `message`
  - dataclass event with `.type`/`.message`
  - string event
  - unknown object → safe string (no crash)
- core logic never returns empty assistant message (fallback is used)

If you add the adapter, test `extract_final_assistant_text()` too.

---

## Manual verification (Copilot must run + paste outputs)
1) `pytest -q`
2) `.venv/bin/streamlit run app/ui/streamlit_app.py`
3) In UI:
- send `hi` → assistant replies (not empty)
- send `show me 10 rows from v_dlv_dep_prty_clr`
  - assistant responds with results summary
  - Activity Log streams events when Debug ON

---

## Acceptance Criteria
- TD-styled UI (white/green, clean cards).
- Assistant message is NEVER empty.
- Activity Log streams and can be hidden with Debug toggle.
- No heavy deps added.
- `pytest -q` passes.

Now implement, run verification commands, and paste:
- `pytest -q` output
- Streamlit startup output + one interaction log
