# Prompt: Fix Streamlit crash — `NameError: name 'OrchestratorClient' is not defined` (and validate type-hint safety)

You are working in repo **text2sql_v2**. The Streamlit UI crashes at import time with:

- `NameError: name 'OrchestratorClient' is not defined`
- Trace points to: `app/ui/streamlit_app.py`, around the function signature:
  - `def render_chat_main(orchestrator: OrchestratorClient) -> None:`

This happens because **Python evaluates annotations at function definition time** (unless postponed), and `OrchestratorClient` is **not in scope** at that moment (it’s imported only inside `main()` or later).

Your job:
1) Fix the crash in a **clean, production-grade** way.
2) Validate that **no other file** has the same “runtime-evaluated type hint” problem.
3) Keep runtime imports minimal (avoid circular import traps).
4) Run tests + a Streamlit smoke run to confirm.

---

## Constraints

- **Do not** change public behavior of the app.
- **Do not** remove useful typing; make it safe.
- Keep existing architecture (SearchDecider / OrchestratorFacade / ActivityStream etc.) intact.
- Prefer changes that prevent this class of error from recurring.

---

## Step 1 — Fix `OrchestratorClient` NameError in `app/ui/streamlit_app.py`

### Option A (preferred): Postpone evaluation of all annotations in the module

1) Edit `app/ui/streamlit_app.py`
2) Ensure the very first import is:

```python
from __future__ import annotations
```

> It must appear at the top of the file (after an optional module docstring, before other imports).

3) Keep `OrchestratorClient` imported where you want it at runtime (it can remain inside `main()`), but **typing will now be safe**.

### Option B: Use `TYPE_CHECKING` + forward reference string (also good)

If you don’t want `__future__` for some reason, then:

1) At the top of `app/ui/streamlit_app.py`, add:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ui.orchestrator_client import OrchestratorClient
```

2) Change the function signature to a string annotation:

```python
def render_chat_main(orchestrator: "OrchestratorClient") -> None:
    ...
```

This avoids importing `OrchestratorClient` at import time and prevents runtime NameError.

✅ Either Option A or B is acceptable. **Option A is simpler and prevents future similar issues in this file.**

---

## Step 2 — Confirm the runtime import plan is correct

In `app/ui/streamlit_app.py` ensure:

- `OrchestratorClient` (or facade client) is instantiated **inside** `main()`:

```python
from app.ui.orchestrator_client import OrchestratorClient
orchestrator = OrchestratorClient()
```

- `render_chat_main(orchestrator)` is called after that.
- No module-level code executes `OrchestratorClient()` on import.

---

## Step 3 — Validate other modules for the same problem

Search the repo for type hints that reference names **not imported in that module**.

Run these searches (or equivalent):

- Look for annotations referencing OrchestratorClient:
  - `OrchestratorClient`
- More generally search for patterns like:
  - `: SomeClass`
  - `-> SomeClass`
  - where `SomeClass` is not imported.

Checklist:
1) Any file that has a function signature referencing a class **only imported inside a function** is a candidate for this NameError.
2) Fix using one of:
   - `from __future__ import annotations`
   - `TYPE_CHECKING` + `"ForwardRef"`
   - replace with a protocol/interface type (only if you already have one)
   - `Any` as a last resort (avoid if possible)

**Apply the same safe pattern consistently** across `app/ui/*.py`.

---

## Step 4 — Add a guardrail (recommended)

To prevent repeats, do this:

- Add `from __future__ import annotations` to all UI modules that are Streamlit entrypoints or likely to have runtime imports (at least `app/ui/streamlit_app.py`, optionally others in `app/ui/`).

This is safe in Python 3.11 and reduces annotation-related import-time failures.

---

## Step 5 — Verify with commands

### 5.1 Unit tests
Run:

```bash
.venv/bin/pytest -q
```

All tests must pass.

### 5.2 Streamlit smoke test
Run:

```bash
.venv/bin/streamlit run app/ui/streamlit_app.py
```

Acceptance criteria:
- App loads with no red traceback.
- The “Text2SQL Chat” page renders.
- Chat input works.
- Activity log still updates.

---

## Deliverables

When you implement the fix, provide:

1) A short explanation of **why** the NameError happened (annotation evaluation) and what you changed.
2) Exact code diff (or file patches) for `app/ui/streamlit_app.py`.
3) List of any other files you updated for annotation safety.
4) Proof steps you ran:
   - pytest output summary
   - Streamlit start confirmation (no crash)

---

## Quick expected patch (example)

If using Option A, the top of `app/ui/streamlit_app.py` should look like:

```python
from __future__ import annotations

import sys
from pathlib import Path
import streamlit as st
...
```

and you can keep:

```python
def render_chat_main(orchestrator: OrchestratorClient) -> None:
    ...
```

because the annotation is now postponed.

---

## If anything is unclear

If you need more context, request:
- The **top 60 lines** of `app/ui/streamlit_app.py`
- The `app/ui/orchestrator_client.py` class signature
- Any other file where `OrchestratorClient` is used in type hints

But do **not** guess. Confirm with the actual code.
