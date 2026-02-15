# Copilot Prompt — Fix Streamlit UI: blank main page (render chat in main area)

## Goal
Your Streamlit app currently renders the **sidebar** (“Data source & Session”) but the **main page is blank**.  
Update the UI so the **main area always shows a chat interface** where the **user + agent collaborate**.

The chat must:
- Show a running **chat transcript** (user + assistant messages).
- Include a **chat input** at the bottom.
- Stream an **activity / thought-process log** (e.g., “Deciding if search is needed…”, “Fetching from AI Search…”, “Reviewing table schema…”, “Running SQL…”, “Summarizing results…”).
- When SQL returns rows, the **dataset preview must be sent back into the LLM** so the assistant can explain/summarize in chat (do not only show a dataframe without assistant commentary).

**Important:** Do not “redesign” the product. Implement the required structure + methods and make the chat appear in main content reliably.

---

## Context / Symptom
- Page loads (no crash), sidebar is visible.
- Main content area is empty/blank.
- Expected: chat on main page.

This symptom usually means one of these is happening:
- `st.stop()` / early `return` occurs after sidebar render, before main render.
- Main render is inside a condition that isn’t met (e.g., “metadata loaded” / “index selected”).
- Custom CSS hides main container (e.g., `display:none`, `height:0`, overlay).
- Main UI is written into an `st.empty()` placeholder that is never filled.

---

## Files to inspect (do NOT guess—inspect repo)
1. `app/ui/streamlit_app.py` (primary)
2. Any helpers referenced by the UI (existing in repo if present):
   - `app/ui/chat_models.py`
   - `app/ui/activity_stream.py`
   - `app/ui/search_decider.py`
3. Orchestrator entrypoint used by UI:
   - `app/core/orchestrator_facade.py` (or equivalent)

---

## Required UI architecture (implement exactly)
### 1) `app/ui/streamlit_app.py`
Create/ensure these functions exist and are used **in this order**:

#### `bootstrap_project_root() -> None`
- Ensures project root is in `sys.path` so imports like `from app.core...` work reliably when Streamlit runs.
- Must run **before** importing internal `app.*` modules that may fail in Streamlit.

#### `inject_css() -> None`
- Inject all CSS inside **one** `st.markdown(\"\"\"<style>...</style>\"\"\", unsafe_allow_html=True)` call.
- Do **not** leave stray CSS lines in Python scope.
- Ensure CSS does **not** hide the main area. Specifically, do NOT set:
  - `.main { display:none; }`
  - `.block-container { height: 0; overflow: hidden; }`
  - overlays with `position: fixed` covering the page.

#### `init_session_state() -> None`
Must set defaults so the UI never crashes and never becomes blank due to missing state:
- `st.session_state.messages: list[dict]` (each dict at least `{role, content}`)
- `st.session_state.activity: list[str]`
- `st.session_state.debug_enabled: bool` (default `False`)
- Any UI options should always have a default object/dict (never `None`).

#### `render_sidebar() -> None`
- Keep your existing sidebar controls (indexes list, refresh metadata, download json, clear chat).
- **Do not** call `st.stop()` in the sidebar logic.
- If something is missing (no indexes, metadata not loaded), show a warning in sidebar but continue rendering main chat.

#### `render_chat_main(orchestrator) -> None`
This is the key fix:
- Must ALWAYS render something in the main area on every run:
  - Title/header (e.g., “Text2SQL Chat”)
  - Chat transcript
  - Chat input
  - Activity panel (expander / status component)

Pseudo-UI requirements:
- Show transcript with `st.chat_message(role)` for each message.
- If transcript is empty, add an initial assistant greeting message (“Hi — ask me a question…”).
- Add `st.chat_input(...)` at bottom for user input.
- The activity log must update while processing a turn (streaming).

#### `main() -> None`
Must follow this high-level order:

1) `st.set_page_config(...)`
2) `bootstrap_project_root()`
3) Import internal modules (orchestrator, helpers)
4) `inject_css()`
5) `init_session_state()`
6) `render_sidebar()`
7) `render_chat_main(orchestrator)`  ✅ this must run unconditionally

---

## Required backend contract (UI ↔ orchestrator)
### 2) Orchestrator method (create if missing; otherwise adapt)
In `app/core/orchestrator_facade.py`, expose a single UI-friendly entrypoint:

#### `run_chat_turn(user_text: str, *, max_rows: int, debug: bool) -> dict`
Return a dict with:
- `assistant_text: str` (final assistant message)
- `activity: list[str]` (ordered log lines for UI streaming)
- Optional `sql: str`
- Optional `rows: list[dict]` (preview rows)
- Optional `columns: list[str]`
- Optional `error: str`

**Critical requirement:** If `rows` is present, the orchestrator must pass a compact preview (e.g., first 10–50 rows) into the LLM so the assistant message includes an explanation/summary, not just raw rows.

---

## “Search or not” decision requirement
### 3) Deterministic search decision
Implement (or confirm) a function used by the orchestrator:

#### `decide_use_search(user_text: str) -> tuple[bool, str]`
Returns:
- `use_search: bool`
- `reason: str` (must be appended to activity log)

Rule: If the question is general (“what is…”, help, non-table question), do NOT hit AI Search. If the question needs schema/metadata/table discovery, DO use search.

---

## How to fix the blank main page (explicit steps)
1. In `app/ui/streamlit_app.py`, **find any `st.stop()` or early `return`** before the main render.
   - Replace with warnings + continue.
2. Find any conditions gating main rendering (e.g., `if not indexes: ...`).
   - Ensure chat renders regardless; show warning inside chat area if prerequisites missing.
3. Add a temporary visible marker at the top of main:
   - `st.write(\"[DEBUG] main rendered\")`
   - If you still don’t see it, CSS is hiding content—fix CSS.
4. Ensure `render_chat_main()` is called on every script run.
5. Ensure `st.chat_input()` is not inside a condition that might skip.

---

## Acceptance criteria
- Opening the app shows:
  - Sidebar controls on left
  - Chat UI in main area (always visible)
- Sending a message:
  - Adds user message to transcript
  - Shows assistant streaming activity log while processing
  - Shows assistant answer in chat
  - If SQL executed and rows returned:
    - UI can display a dataframe preview
    - Assistant message includes a summary derived from those rows

---

## Verification commands
Run these and paste any errors if they occur:
- `python -m compileall app/ui/streamlit_app.py`
- `streamlit run app/ui/streamlit_app.py`
- Open the Local URL and confirm chat appears in main.

---

## If you need more context
If you cannot find where main content is being suppressed, ask me to paste:
- `app/ui/streamlit_app.py` (entire file)
- Any helper imported by it (`activity_stream.py`, `chat_models.py`, `search_decider.py`)
- The orchestrator entrypoint (`app/core/orchestrator_facade.py`)
