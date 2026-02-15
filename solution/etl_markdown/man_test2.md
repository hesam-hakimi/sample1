# Prompt for Copilot/Codex: Fix failing pytest `test_get_ui_options_returns_instance`

## Context
You are working in repo `text2sql_v2`. Running tests shows **one failing test**:

- `app/ui/test_state.py::test_get_ui_options_returns_instance`
- Failure symptom: when the test sets `st.session_state["max_rows"] = 77` (and other keys), `get_ui_options()` still returns defaults (e.g., `max_rows=50`), so the assertion `assert options.max_rows == 77` fails.

This indicates `get_ui_options()` is **not reading Streamlit session state correctly** (common causes: importing `session_state` directly, caching a reference, or always returning `DEFAULT_UI_OPTIONS`).

## Goal
Make **all tests pass** (`pytest -q`), specifically:
- `get_ui_options()` must return a **UIOptions instance**
- It must honor **valid values** from `st.session_state`
- It must **sanitize invalid values** (fall back to defaults)
- It must be compatible with monkeypatching in tests

## Non-negotiable API / Signatures (do not change)
Keep these names and signatures as-is (because UI + tests depend on them):

### `app/ui/models.py`
```py
@dataclass(frozen=True)
class UIOptions:
    max_rows: int
    execution_target: Literal["sqlite", "oracle"]  # oracle is placeholder
    debug_enabled: bool
```

### `app/ui/state.py`
```py
DEFAULT_UI_OPTIONS: UIOptions

def get_ui_options() -> UIOptions:
    ...
```

> You may add helper functions in `state.py`, but do **not** change the public signatures above.

---

## Root cause to fix
The test does:
```py
monkeypatch.setattr(st, "session_state", {})
st.session_state["max_rows"] = 77
...
options = get_ui_options()
assert options.max_rows == 77
```
This will only work if `get_ui_options()` reads **`streamlit.session_state` dynamically via `import streamlit as st`**.

If `state.py` does any of these, the monkeypatch won’t work and the test will fail:
- `from streamlit import session_state` (captures reference)
- `from streamlit.runtime.state import SessionState` (captures implementation)
- caching `session_state` into a module global
- returning `DEFAULT_UI_OPTIONS` without checking session state

---

## Required implementation behavior
### 1) Always import streamlit as a module (important for monkeypatch)
In `app/ui/state.py` (module scope):
```py
import streamlit as st
```

### 2) `get_ui_options()` must:
- Read `st.session_state` safely (even if empty or missing)
- Look for these keys (exact names):
  - `"max_rows"` → int
  - `"execution_target"` → `"sqlite"` or `"oracle"`
  - `"debug_enabled"` → bool
- Validate/sanitize:
  - `max_rows` must be `int` and **> 0** (you can also enforce an upper bound like 500/1000 if you want)
  - `execution_target` must be allowed
  - `debug_enabled` must be bool
- If invalid/missing, fall back to `DEFAULT_UI_OPTIONS.<field>`
- Return a new `UIOptions(...)` instance

### 3) Optional but recommended
Write sanitized values back into `st.session_state` so the UI stays consistent. This won’t break tests.

---

## Exact patch to implement (copy/paste friendly)
Open `app/ui/state.py` and ensure you have something like this (adapt only if your file already has overlapping helpers):

```py
from __future__ import annotations

from typing import Any, Optional
import streamlit as st

from app.ui.models import UIOptions

DEFAULT_UI_OPTIONS = UIOptions(
    max_rows=50,
    execution_target="sqlite",
    debug_enabled=False,
)

_ALLOWED_EXEC_TARGETS = {"sqlite", "oracle"}

def _coerce_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):  # bool is int subclass, exclude it
        return None
    if isinstance(value, int):
        return value
    return None

def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    return None

def _coerce_exec_target(value: Any) -> Optional[str]:
    if isinstance(value, str) and value in _ALLOWED_EXEC_TARGETS:
        return value
    return None

def get_ui_options() -> UIOptions:
    """Return UI options from Streamlit session state. Never returns None."""
    ss = getattr(st, "session_state", None)
    if ss is None:
        ss = {}

    # max_rows
    raw_max_rows = ss.get("max_rows", DEFAULT_UI_OPTIONS.max_rows) if hasattr(ss, "get") else DEFAULT_UI_OPTIONS.max_rows
    max_rows = _coerce_int(raw_max_rows)
    if max_rows is None or max_rows <= 0:
        max_rows = DEFAULT_UI_OPTIONS.max_rows

    # execution_target
    raw_target = ss.get("execution_target", DEFAULT_UI_OPTIONS.execution_target) if hasattr(ss, "get") else DEFAULT_UI_OPTIONS.execution_target
    execution_target = _coerce_exec_target(raw_target) or DEFAULT_UI_OPTIONS.execution_target

    # debug_enabled
    raw_debug = ss.get("debug_enabled", DEFAULT_UI_OPTIONS.debug_enabled) if hasattr(ss, "get") else DEFAULT_UI_OPTIONS.debug_enabled
    debug_enabled = _coerce_bool(raw_debug)
    if debug_enabled is None:
        debug_enabled = DEFAULT_UI_OPTIONS.debug_enabled

    options = UIOptions(
        max_rows=max_rows,
        execution_target=execution_target,  # type: ignore[arg-type] if Literal complains
        debug_enabled=debug_enabled,
    )

    # Optional: persist sanitized values for the UI
    try:
        st.session_state["max_rows"] = options.max_rows
        st.session_state["execution_target"] = options.execution_target
        st.session_state["debug_enabled"] = options.debug_enabled
    except Exception:
        pass

    return options
```

### Important notes
- **Do not** use `from streamlit import session_state`
- If you already have `DEFAULT_UI_OPTIONS` defined elsewhere, keep its values but ensure behavior matches the test.
- If `UIOptions.execution_target` is a `Literal[...]`, you may need a small `# type: ignore[arg-type]` on assignment.

---

## Verification steps (must do)
Run these commands and confirm results:

```bash
# 1) Run only failing test
.venv/bin/pytest -q app/ui/test_state.py::test_get_ui_options_returns_instance

# 2) Run full suite
.venv/bin/pytest -q
```

Expected:
- `test_get_ui_options_returns_instance` passes
- All tests pass (`0 failed`)

---

## If it still fails
Do this investigation and fix accordingly (do not stop at guessing):
1. Open `app/ui/test_state.py` and confirm the expected keys and values.
2. Add temporary debug prints in `get_ui_options()` to log what it reads from session state (remove prints before final commit).
3. Search for any `from streamlit import session_state` patterns:
   ```bash
   rg -n "from\s+streamlit\s+import\s+session_state|session_state\s*=|SessionState" app/ui
   ```
   Replace those usages with `import streamlit as st` + `st.session_state`.

---

## Deliverables
- Updated `app/ui/state.py` (or the correct file where `get_ui_options()` lives)
- All tests passing (`pytest -q`)
- No signature changes to `UIOptions` or `get_ui_options()`
