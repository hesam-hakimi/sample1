# Prompt: Fix `NameError: name 'st' is not defined` in `app/ui/streamlit_app.py`

You are working in the repo **text2sql_v2**. Running the Streamlit UI fails immediately with:

- **NameError: name `st` is not defined**
- It happens at/near the very top of `app/ui/streamlit_app.py` where `st.set_page_config(...)` is called.

This is a **runtime import/ordering bug**, not a design change request.

---

## Objective

1. Fix the crash so the Streamlit app loads.
2. Preserve the **chat-first UI architecture** already implemented (chat transcript, chat input, streaming activity log).
3. Do **minimal, surgical changes** (do not redesign the UI; do not add new features).

---

## Constraints

- Do not remove the chat UI code that was recently added (e.g., `render_chat_main(...)`, activity log, `run_chat_turn`, etc.).
- Do not introduce new frameworks.
- Keep Streamlit usage idiomatic:
  - `st.set_page_config(...)` must be called **once per page run**, and it must execute **after `import streamlit as st`** and before other Streamlit calls.
- Ensure the file can be imported/executed without relying on side effects from other modules.

---

## Root Cause (what to look for)

This error means **`st` is referenced before it is defined**. Typical causes:

- `import streamlit as st` is missing.
- `import streamlit as st` exists, but it’s *below* `st.set_page_config(...)` or inside a function, while `st.set_page_config(...)` runs at module import time.
- A refactor moved `st.set_page_config(...)` above imports or into a block that runs before the import.

---

## Required Fix (Implementation Details)

### Step 1 — Open and inspect
- Open `app/ui/streamlit_app.py`.
- Confirm where `st.set_page_config(...)` is called.
- Confirm whether `import streamlit as st` exists and where it is located.

### Step 2 — Ensure correct import order (must do)
Reorder the top of `app/ui/streamlit_app.py` to the following pattern:

1. Optional future import (if used):
   - `from __future__ import annotations`
2. Standard library imports (`os`, `sys`, `pathlib`, `typing`, etc.)
3. **Project-root bootstrap** (if you are using one) that modifies `sys.path`
4. **`import streamlit as st`**
5. Then call `st.set_page_config(...)`

> **Important:** If your code currently calls `st.set_page_config(...)` at module top-level, keep it there — but only *after* `import streamlit as st`.  
> If `st.set_page_config(...)` is called inside `main()`, ensure `import streamlit as st` is at file top-level anyway (simplest, safest).

### Step 3 — Keep `main()` and rendering flow intact
- Ensure there is a `main()` that orchestrates:
  - page config (if not already done at top-level),
  - sidebar rendering,
  - `render_chat_main(orchestrator)` (or similar),
  - activity log expander.
- Ensure the file ends with `main()` being executed once.
  - Avoid double-execution (don’t call `main()` twice; don’t call it both with and without `if __name__ == "__main__":`).

### Step 4 — Don’t break the imports of other modules
Your repo likely has modules like:
- `app/core/orchestrator_facade.py`
- `app/ui/activity_stream.py`
- `app/ui/chat_models.py`
- `app/ui/search_decider.py`

Do **not** change their APIs unless you find an actual import error.

---

## Verification (run these commands)

Use the venv Python and venv Streamlit **explicitly**:

```bash
# From repo root
/app1/tag5916/projects/text2sql_v2/.venv/bin/python -m compileall app/ui/streamlit_app.py

# Start the UI
/app1/tag5916/projects/text2sql_v2/.venv/bin/streamlit run app/ui/streamlit_app.py
```

**Expected result:**
- No `NameError`.
- Page renders with chat area visible in the **main panel** (not blank).
- Sidebar can exist, but main panel must show chat transcript + input.

---

## Deliverables

1. A patch to `app/ui/streamlit_app.py` that fixes the crash.
2. Brief note in the PR/commit message explaining:
   - `st` was used before import,
   - import order fixed.

---

## Definition of Done

- `streamlit_app.py` runs without exceptions.
- Chat UI is visible in the main page immediately on load.
- No unrelated refactors or UI redesigns were introduced.
