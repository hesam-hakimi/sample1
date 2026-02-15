# Prompt for GitHub Copilot (Agent) — Fix `TraceEvent.__init__()` unexpected keyword `stage`

## Goal
Your Streamlit app crashes on greeting (“hi”) with:

`TypeError: TraceEvent.__init__() got an unexpected keyword argument 'stage'`

This occurs inside `app/ui/orchestrator_client.py` when it calls:

`TraceEvent(ts_iso=..., stage="intent", message="...")`

So `TraceEvent` in `app/ui/models.py` (or wherever it’s defined/imported from) does **not** currently accept a `stage` keyword.

## What you must deliver
1. **Fix the crash** by making `TraceEvent` compatible with the usage `TraceEvent(ts_iso=..., stage=..., message=...)`.
2. Ensure **all tests pass** (`pytest -q`).
3. Ensure **Streamlit runs** (`streamlit run app/ui/streamlit_app.py`) and greeting messages do not crash.
4. Do **not** change public behavior of the app except fixing the error and keeping trace streaming working.

---

## Step-by-step plan (do in this order)

### 1) Locate the authoritative `TraceEvent` definition
- Open `app/ui/models.py` (or the file that defines `TraceEvent` imported by `app/ui/orchestrator_client.py`).
- Confirm which `TraceEvent` class is actually imported:
  - In `app/ui/orchestrator_client.py`, find `from .models import ... TraceEvent ...` (or similar).
  - Ensure you are editing the same `TraceEvent`.

### 2) Standardize `TraceEvent` to support `stage` + `message`
Update the `TraceEvent` model so it accepts these fields:

- `ts_iso: str`
- `stage: str`
- `message: str`
- optionally:
  - `detail: str | None = None`
  - `payload: dict | None = None`

#### Preferred implementation (simple + robust)
Use a dataclass:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass(frozen=True)
class TraceEvent:
    ts_iso: str
    stage: str
    message: str
    detail: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
```

**Important:**  
- If the file already has `from __future__ import annotations`, it MUST be the **very first import** (line 1) with no blank lines or code before it.
- If there are duplicates, remove duplicates and keep only one at the very top.

### 3) Backward compatibility (if older fields exist)
If the existing `TraceEvent` is currently used elsewhere with a different kwarg name (e.g., `kind`, `event`, `label`, `step`, `msg`), do one of these:

**Option A (preferred): Update call sites**
- `rg "TraceEvent\(" app/ui -n`
- Update all usages to use `stage=` and `message=`.

**Option B: Provide aliases**
If you want to avoid touching many call sites, you can keep the canonical fields and add a constructor helper:

```python
    @staticmethod
    def from_legacy(
        ts_iso: str,
        *,
        kind: str | None = None,
        label: str | None = None,
        msg: str | None = None,
        message: str | None = None,
        stage: str | None = None,
        **kw,
    ) -> "TraceEvent":
        return TraceEvent(
            ts_iso=ts_iso,
            stage=stage or kind or label or "info",
            message=message or msg or "",
            payload=kw or None,
        )
```

…but **only** do this if you actually find legacy usage patterns in this repo.

### 4) Ensure the UI rendering matches the model
In `app/ui/streamlit_app.py`, the activity log rendering uses:

- `e.stage`
- `e.message`

Confirm those attributes exist on `TraceEvent` after your change.

### 5) Fix `orchestrator_client.py` (only if needed)
The crash shows it passes `stage=` already, so it’s probably fine.  
But verify that every `TraceEvent(...)` call uses only valid kwargs after step 2.

### 6) Add a regression test to prevent this from breaking again
Create or update a test file (pick an existing test module under `app/ui/`):

Example: `app/ui/test_models.py`

```python
from app.ui.models import TraceEvent

def test_traceevent_accepts_stage_and_message():
    ev = TraceEvent(ts_iso="2026-01-01T00:00:00", stage="intent", message="hello")
    assert ev.stage == "intent"
    assert ev.message == "hello"
```

If you already have tests around trace events, just add assertions there.

### 7) Verification commands (must run and pass)
Run these in order and ensure no failures:

```bash
.venv/bin/pytest -q
.venv/bin/streamlit run app/ui/streamlit_app.py
```

**Manual UI sanity:**
- Type: `hi`
- Expected:
  - assistant replies with greeting
  - activity log still renders (even if empty)
  - no crash

---

## Acceptance criteria (checklist)
- [ ] `TraceEvent(ts_iso=..., stage=..., message=...)` works everywhere (no TypeError)
- [ ] `pytest -q` passes
- [ ] Streamlit app loads and accepts input without crash
- [ ] `TraceEvent` field names match UI rendering (`stage`, `message`)
- [ ] `from __future__ import annotations` appears **once** and at the very top of each file that uses it

---

## Notes (do NOT ignore)
- Keep changes minimal and localized to `TraceEvent` and any direct call sites.
- Do not refactor unrelated UI code.
- If you find multiple competing `TraceEvent` definitions (duplicate classes in other files), remove duplication and keep a **single canonical model** in `app/ui/models.py`, and import it everywhere else.

