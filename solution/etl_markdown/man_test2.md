# Fix Streamlit crash: `AttributeError: 'NoneType' object has no attribute 'debug_enabled'`

## Context
When running the Streamlit UI:

```bash
.venv/bin/streamlit run app/ui/streamlit_app.py
```

the app crashes with:

```text
AttributeError: 'NoneType' object has no attribute 'debug_enabled'
File ".../app/ui/streamlit_app.py", line 87, in <module>
    if options.debug_enabled:
```

This indicates `options` is `None` at runtime.

---

## Your task (Copilot Agent)
### Goal
Fix the crash **without redesigning the UI**. Ensure `options` is **always** a valid `UIOptions` instance (never `None`), with sensible defaults.

### Constraints
- Do **not** redesign or refactor the UI flow beyond what is needed to fix this bug.
- Preserve existing UX and layout.
- Make the fix robust: no `None` options in any execution path.

---

## Expected code structure (must match)
You already have a dataclass like:

```python
@dataclass
class UIOptions:
    max_rows: int
    execution_target: Literal["sqlite", "oracle"]
    debug_enabled: bool
```

There must be **one** canonical place that creates/loads UI options, e.g.:
- `app/ui/state.py` (preferred), OR
- `app/ui/chat_models.py` (if that’s where you put UI models)

Call it something like:

```python
def load_ui_options() -> UIOptions:
    ...
```

or

```python
def get_ui_options() -> UIOptions:
    ...
```

**Important:** This function must **always** return `UIOptions(...)` and never `None`.

---

## Root cause (what to look for)
In `app/ui/streamlit_app.py` the variable `options` is being assigned from a function that can return `None`, for example:
- returning `None` when env vars are missing
- returning `None` when config load fails
- returning `None` if `st.session_state` doesn’t have a key yet

---

## Required fix (implement these)
### 1) Make option-loading total (never returns `None`)
Find where `options` is created (search for `UIOptions(`, `get_ui_options`, `load_ui_options`, `options =`).

Update the option loader to:
- provide defaults if env/config is missing
- catch parsing errors and fallback to defaults
- optionally write a warning to Streamlit (only if `debug_enabled` is True OR if you already have a logger)

Example pattern:

```python
DEFAULT_UI_OPTIONS = UIOptions(
    max_rows=50,
    execution_target="sqlite",
    debug_enabled=False,
)

def load_ui_options() -> UIOptions:
    try:
        # read env/config/session_state, validate
        ...
        return UIOptions(...)
    except Exception:
        return DEFAULT_UI_OPTIONS
```

### 2) Add a defensive fallback in `streamlit_app.py`
Even with a correct loader, make the UI file safe:

```python
options = load_ui_options()
if options is None:
    options = DEFAULT_UI_OPTIONS
```

Then use `options.debug_enabled` safely.

### 3) Validate/normalize inputs
If `execution_target` is read from env/config, normalize:
- accept case-insensitive values (`SQLITE`, `sqlite`)
- if invalid -> fallback to `"sqlite"`

If `max_rows` is read from env/config, ensure it’s an `int` with bounds:
- `1 <= max_rows <= 1000` (or your chosen bound)
- invalid -> fallback to default

### 4) Tests (minimum)
Add a small unit test ensuring the loader never returns `None`.

Example (pytest):
- if env vars are absent -> returns defaults
- if env vars are invalid -> returns defaults

---

## Acceptance criteria (must pass)
1. Running Streamlit no longer crashes:
   ```bash
   .venv/bin/streamlit run app/ui/streamlit_app.py
   ```
2. `options` is never `None` in `streamlit_app.py`.
3. A unit test confirms the loader returns a `UIOptions` instance in all cases.
4. No UI redesign.

---

## Helpful commands
From repo root:

```bash
# quick syntax check
python -m compileall app/ui/streamlit_app.py

# run app
.venv/bin/streamlit run app/ui/streamlit_app.py

# run tests (if you have pytest)
pytest -q
```

---

## Deliverables
- Updated option loader (`load_ui_options()` / `get_ui_options()`).
- Updated `app/ui/streamlit_app.py` with a defensive fallback.
- New/updated tests verifying non-None options.
