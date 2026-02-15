## Copilot / Codex Prompt — Fix Streamlit errors (NameError `display` + ModuleNotFoundError `No module named 'app'`)

You are working in this repo (Linux path example): `/app1/tag5916/projects/text2sql_v2/`

### Goal
Make `streamlit run app/ui/streamlit_app.py` work reliably with:
1) **No stray CSS interpreted as Python** (fix `NameError: name 'display' is not defined`)
2) **No import failure** (fix `ModuleNotFoundError: No module named 'app'`)
3) Keep changes minimal + safe. Do not change business logic.

---

## What to do (REQUIRED)

### 1) Fix the stray CSS → Python issue
- Open `app/ui/streamlit_app.py`
- Find any lines like `display: inline-block;` or other CSS properties that exist as raw Python statements.
- Move ALL CSS into a single helper like:

- `def inject_css(): st.markdown("""<style> ... </style>""", unsafe_allow_html=True)`
- Call `inject_css()` once near the top (after imports and `st.set_page_config`).

✅ Result: no `NameError: display is not defined` and no “CSS lines in Python scope”.

---

### 2) Fix `ModuleNotFoundError: No module named 'app'`
This happens because Streamlit’s working directory / sys.path doesn’t include the project root, so `from app.core...` fails.

Implement **ONE** of the following solutions (prefer A; use B if packaging already exists):

#### Option A (minimal + reliable): add project-root bootstrap to sys.path
At the top of `app/ui/streamlit_app.py` (before `from app.core...` imports), add:

- `from pathlib import Path`
- `import sys`
- `PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../text2sql_v2`
- `sys.path.insert(0, str(PROJECT_ROOT))` only if not already present.

Then keep the normal import:
- `from app.core.orchestrator_facade import run_question`

#### Option B (packaging): ensure `app` is a real package and install it
- Ensure these files exist (create if missing):
  - `app/__init__.py`
  - `app/core/__init__.py`
  - `app/ui/__init__.py`
- If repo has `pyproject.toml` / `setup.py`, run editable install:
  - `pip install -e .`
- Then imports should work without sys.path hacks.

✅ Result: Streamlit can import `app.*` when run from anywhere.

---

## Verification (MUST RUN and report results)
Run from repo root: `/app1/tag5916/projects/text2sql_v2`

1) Syntax check:
- `python -m compileall app/ui/streamlit_app.py`

2) Import check:
- `python -c "import app; import app.core.orchestrator_facade; print('imports OK')"`

3) Run Streamlit:
- `.venv/bin/streamlit run app/ui/streamlit_app.py`
  (or `python -m streamlit run app/ui/streamlit_app.py`)

✅ App should load at `http://localhost:8501` without traceback.

---

## Output format (IMPORTANT)
- Provide a **single patch** (diff) or edited file content for `app/ui/streamlit_app.py`
- If you create `__init__.py` files, include them too.
- Then list the exact commands used for verification + their outputs (short).
- Do NOT add extra explanations beyond what’s needed.
