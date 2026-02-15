# Text2SQL UI – Fix `__future__` Import Error + Consistency Checklist

**Current blocker you’re seeing**

```
SyntaxError: from __future__ imports must occur at the beginning of the file
File: app/ui/state.py (line ~10)
```

This is happening while running `pytest` (e.g., `app/ui/test_state.py` imports `app.ui.state`), so tests fail before they even execute.

---

## 1) Root cause (what’s actually wrong)

Python requires any `from __future__ import ...` statements to appear **before any other non‑docstring statements** in a module.

Allowed before the `__future__` import:
- A **module docstring** (triple-quoted string at top)
- **Comments** (recommended)
- `# -*- coding: utf-8 -*-` encoding header (rare nowadays)

**Not allowed** before the `__future__` import:
- Any `import ...`
- Any assignments / constants
- Any function / class definitions
- Any other executable statements

What usually triggers this in your case:
- Copilot inserted **multiple** `from __future__ import annotations` lines,
- and at least one of them is **not at the top** (e.g., after `import streamlit as st`), which breaks module import.

---

## 2) Fix (do this first)

### 2.1 Edit `app/ui/state.py`

**Goal:** Ensure there is **exactly one** `from __future__ import annotations`, and it is at the very top (after optional module docstring/comments).

**Expected file header pattern (example):**
```python
\"\"\"UI session-state helpers for the Streamlit Text2SQL app.\"\"\"

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, List, Dict
import os

import streamlit as st
```

### 2.2 What to change exactly

1. **Open** `app/ui/state.py`
2. **Search** for `from __future__ import annotations`
3. Do both:
   - Keep **only one** occurrence
   - Move that one occurrence to the very top (after module docstring if present)
4. Ensure there are **no imports** (like `import streamlit as st`) before the `__future__` import.
5. Save the file.

> Tip: If you want a module docstring, it must be the very first statement. The `__future__` import must come right after the docstring.

---

## 3) Verification (must pass)

Run these commands from repo root:

### 3.1 Compile-time check (fast)
```bash
python -m compileall app/ui -q
```
If this fails, you still have an import-time issue.

### 3.2 Unit tests
```bash
pytest -q
```
Expected: all tests pass.

### 3.3 Run Streamlit
```bash
streamlit run app/ui/streamlit_app.py
```
Expected: app loads and chat UI renders.

---

## 4) Prevent this from coming back (recommended)

### 4.1 Rule of thumb for Copilot
Whenever Copilot suggests adding `from __future__ import annotations`:
- **Do it only once per file**
- Put it at the **top**
- Never add it in the middle of a file

### 4.2 Alternative (if you want to avoid `__future__` entirely)
Instead of `from __future__ import annotations`, you can:
- Use **string annotations**:
  ```python
  def render_chat_main(orchestrator: "OrchestratorClient") -> None:
      ...
  ```
- Or use `typing.TYPE_CHECKING` + local imports.

But since you already started using `__future__`, the simplest is: **keep one at the top**.

---

## 5) Consistency checklist (architecture you want)

This section helps you ensure “all files and implementation are the same as what you want”.

### 5.1 Tool-gating requirement (Search vs No Search)
**Expected behavior:**
- Greeting/smalltalk/help/thanks (e.g., `"hi"`, `"hello"`, `"thanks"`, `"help"`) should **NOT** call:
  - Azure AI Search
  - SQL generation/execution
- It should produce a friendly assistant message only.

**Implementation pattern:**
- `SearchDecider.decide(user_text: str, history: list[ChatMessage], options: UIOptions) -> SearchDecision`
- `SearchDecision` should allow at least:
  - `NO_TOOLS` (greetings/smalltalk/help)
  - `USE_SEARCH_AND_SQL` (real data questions)
  - `ASK_CLARIFICATION` (missing table/time filters, etc.)

**Acceptance criteria:**
- Input `"hi"` ⇒ `SearchDecision.NO_TOOLS` (no search, no SQL)
- Input `"show me top 10 customers by balance"` ⇒ `USE_SEARCH_AND_SQL`

### 5.2 Activity log streaming requirement (“step shows, then fades, then next step…”)
What Streamlit can do reliably:
- Append trace events as they occur (via callback)
- Render newest event at full opacity, older events faded (CSS)
- Optionally show `st.toast(...)` for ephemeral “fade away” feel

**Recommended UX compromise (works well):**
- Activity panel shows a list:
  - newest event: opacity 1.0
  - older events: opacity 0.4–0.6
- Also show `st.toast()` for each new event (auto disappears)

**Acceptance criteria:**
- When running a real question, activity events show in order:
  1) intent detected  
  2) (if needed) search tool called  
  3) prompt build  
  4) SQL generated  
  5) SQL validated  
  6) SQL executed  
  7) results returned  
- New events appear without waiting for the whole turn to finish.

### 5.3 Session-state function signatures (must exist and be imported)
Your Streamlit entrypoint should **only** call functions that exist in `state.py` (or wherever your state helpers live).

At minimum, you should have helpers like:

```python
def init_session_state() -> None: ...
def get_chat_history() -> list[ChatMessage]: ...
def append_chat_message(msg: ChatMessage) -> None: ...

def get_trace_events() -> list[TraceEvent]: ...
def append_trace_event(ev: TraceEvent) -> None: ...
def clear_trace_events() -> None: ...

def get_ui_options() -> UIOptions: ...
def set_ui_options(options: UIOptions) -> None: ...
```

**Acceptance criteria:**
- `streamlit run app/ui/streamlit_app.py` produces **no NameError** for missing state functions.
- `pytest -q` passes.

---

## 6) If you want a Copilot “do this now” patch prompt (copy/paste)

Use this exact prompt in Copilot Chat (in repo root):

> **Prompt to Copilot:**
> 1) Fix `SyntaxError: from __future__ imports must occur at the beginning of the file` in `app/ui/state.py`.  
>    - Ensure there is exactly one `from __future__ import annotations` and it is the first import in the file (after optional module docstring/comments only).  
>    - Remove any duplicate `from __future__ ...` lines.  
> 2) Do not change public function signatures.  
> 3) Run `python -m compileall app/ui -q` and `pytest -q`; include the results.  
> 4) Then run `streamlit run app/ui/streamlit_app.py` and confirm the page loads without NameError.

---

## 7) Quick troubleshooting

### Still seeing the same SyntaxError?
- You still have an `import` / assignment before the `__future__` import.
- Or you have a second `from __future__` later in the file (remove it).

### Tests pass but Streamlit fails with NameError (e.g., `get_trace_events` not defined)
- That’s a **separate** missing symbol issue.
- Fix by adding the function in `state.py` **or** importing it correctly in `streamlit_app.py`.

---

### Done criteria for this step
✅ `python -m compileall app/ui -q` passes  
✅ `pytest -q` passes  
✅ `streamlit run app/ui/streamlit_app.py` loads without SyntaxError/NameError


