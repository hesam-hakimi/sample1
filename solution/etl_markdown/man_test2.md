# Prompt: Fix `NameError: name 'st' is not defined` in `app/ui/streamlit_app.py`

## Context (what you must fix)
Running Streamlit fails immediately with:

- `NameError: name 'st' is not defined`
- Trace points to `app/ui/streamlit_app.py`, line where `st.set_page_config(...)` is called.

From the provided code screenshot, `st.set_page_config(...)` is executed **before** `import streamlit as st`, so `st` is undefined.

## Goal
1. **Fix the crash** by ensuring `streamlit` is imported *before any usage* of `st`.
2. Keep the existing architecture (chat-first UI, activity log, sidebar).
3. Ensure the main page **always shows the chat** (header + messages + input) in the main area.
4. Keep the `sys.path` bootstrap behavior so `from app...` imports work when launched via Streamlit.

## Constraints (important)
- Do **not** redesign the UI or add new features beyond what’s necessary to fix the crash and keep chat visible.
- Prefer minimal, deterministic changes.
- Maintain one authoritative entrypoint flow: `main()` → bootstrap → theme/css → session state → sidebar → chat main.
- `st.set_page_config(...)` must be called **exactly once** and **after** `import streamlit as st`, and **before** other Streamlit UI calls.

---

## Files to change
- `app/ui/streamlit_app.py` (primary)

---

## Required code changes (exact expectations)

### 1) Fix import order and remove the invalid early `st` call
In `app/ui/streamlit_app.py`:

- **Remove** any top-level call like this **that appears before** `import streamlit as st`:
  - `st.set_page_config(page_title="Text2SQL (POC)", page_icon="💡", layout="wide")`

- Ensure imports at the top look like this (order matters):
  1. Standard libs (`sys`, `pathlib`, etc.)
  2. `import streamlit as st`
  3. No `from app...` imports at module top-level if they require project-root bootstrap

### 2) Keep the project-root bootstrap, but don’t block Streamlit
Keep (or implement) a helper like:

- `bootstrap_project_root()` that inserts the project root into `sys.path`

Rules:
- It must run **before any `from app...` imports are executed**.
- It may remain as a function and be called inside `main()` (recommended).
- It may also be called at module load **only if** it does not depend on `app` imports.

### 3) Call `st.set_page_config()` once, in the correct place
Pick **one** of these acceptable patterns (do not do both):

**Preferred pattern**
- Inside `main()` as the first Streamlit call:

```python
def main() -> None:
    st.set_page_config(page_title="Text2SQL (POC)", page_icon="💡", layout="wide")
    bootstrap_project_root()
    ...
```

Alternative pattern (also valid)
- Top-level, but only **after** `import streamlit as st` and before any UI output:

```python
import streamlit as st
st.set_page_config(...)
```

### 4) Make sure `main()` is always called when Streamlit runs the script
Ensure the bottom of the file triggers `main()` under Streamlit execution:

Acceptable guard examples:
```python
if __name__ == "__main__":
    main()
```

or (if you must support special invocation styles):
```python
if __name__ == "__main__" or "streamlit" in sys.argv[0]:
    main()
```

But:
- If you use `"streamlit" in sys.argv[0]`, ensure `sys` is imported before this check.

### 5) Ensure chat renders in main area (no blank page)
Keep the structure already present:

- `render_sidebar()`
- `render_chat_main(orchestrator)`
- `render_trace_panel(...)` (activity log)

Guarantees:
- `render_chat_main(...)` must always run in `main()` after session init, regardless of sidebar state.
- If chat history is empty, insert a greeting message so the main area is not blank.

---

## Acceptance criteria (must pass)
1. `python -m compileall app/ui/streamlit_app.py` succeeds (no syntax errors).
2. `streamlit run app/ui/streamlit_app.py` starts without exceptions.
3. Opening the app shows:
   - A chat header/title in the main area
   - A greeting assistant message if no history exists
   - A chat input at the bottom (e.g., `st.chat_input(...)`)
   - Activity log panel present (or at least not breaking rendering)

---

## Verification commands (run and paste output)
Run from the repo root with the same venv you use for Streamlit:

```bash
.venv/bin/python -m compileall app/ui/streamlit_app.py
.venv/bin/streamlit run app/ui/streamlit_app.py
```

If it still fails, paste:
- the full traceback
- the first ~40 lines of `app/ui/streamlit_app.py` (imports + any early calls)
- the `main()` function definition

---

## Notes (common pitfall to avoid)
- Any `st.*` call above `import streamlit as st` will recreate the same `NameError`.
- Avoid having `st.set_page_config()` twice (Streamlit can warn or behave unexpectedly).
