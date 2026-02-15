## Copilot / Codex Prompt — Fix remaining `NameError: name 'display' is not defined` in Streamlit

You are in repo: `/app1/tag5916/projects/text2sql_v2/`

### Current failure
Running:
- `.venv/bin/streamlit run app/ui/streamlit_app.py`

Still crashes with:
- `NameError: name 'display' is not defined`

This means there is STILL at least one stray CSS line like:
- `display: flex;`
- `display: inline-block;`
(or any `something: something;` line)
**sitting in Python scope** (not inside a string / not inside `st.markdown("""<style>...</style>""")`).

---

## Required fix (DO THIS EXACTLY)

### 1) Find ALL stray CSS-like lines outside strings
In `app/ui/streamlit_app.py`, search for any lines that match CSS property syntax (examples):
- `display: flex;`
- `gap: 8px;`
- `margin-top: 12px;`
- `background: #fff;`

Use ripgrep to catch them:
- `rg -n "^\s*[a-zA-Z_-]+\s*:\s*[^#\n;]+;?\s*$" app/ui/streamlit_app.py`
Also search specifically for display:
- `rg -n "^\s*display\s*:" app/ui/streamlit_app.py`

### 2) Move them into ONE CSS injection block (or delete)
Create/keep ONE helper (only one) like:

- `def inject_css():`
  - `st.markdown("""<style> ... ALL CSS HERE ... </style>""", unsafe_allow_html=True)`

Then call `inject_css()` once near the top (after imports and `st.set_page_config`).

**Absolutely no CSS property lines can remain in Python scope.**
If a CSS line is currently sitting between Python code, delete it or move it inside the `<style>` string.

### 3) Prevent future regressions (optional but recommended)
At the very top of the file (first line), add:
- `from __future__ import annotations`
This reduces the chance of “annotation-like” CSS lines evaluating at runtime, but it is NOT a substitute for cleaning the file.

---

## Acceptance criteria (MUST PASS)
Run these commands from repo root:

1) Syntax check:
- `python -m compileall app/ui/streamlit_app.py`

2) Run Streamlit:
- `.venv/bin/streamlit run app/ui/streamlit_app.py`

✅ App loads without `NameError` or traceback.

---

## Output format (IMPORTANT)
- Provide a single patch (diff) for `app/ui/streamlit_app.py`
- Show the exact grep results you found and confirm they are gone after the fix
- Then show the Streamlit run output up to “You can now view your Streamlit app…”
