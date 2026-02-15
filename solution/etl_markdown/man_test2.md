## Prompt: Fix Streamlit `NameError: name 'display' is not defined` (CSS leaked into Python)

You are working in a Python Streamlit repo. Running:

- `streamlit run app/ui/streamlit_app.py`

fails with:

- `NameError: name 'display' is not defined`
- Trace shows `app/ui/streamlit_app.py` around a line like: `display: inline-block;`

### Root cause
Raw CSS property lines (e.g., `display: ...;`, `padding: ...;`) are sitting in **Python scope** (not inside a string). Python tries to execute them as code → `NameError`.

### What to do
1. Open `app/ui/streamlit_app.py`.
2. Find **any CSS-like lines** that are not inside a Python string (search for patterns like `display:`, `padding:`, `margin:`, `border:`, `background:`, `font-`, `color:`).
3. Move **ALL** CSS into a single CSS injection block that runs once near the top of the script, right after imports. Use either:
   - one `st.markdown("""<style>...</style>""", unsafe_allow_html=True)`, or
   - a helper like `def inject_css(): ...` then call it once.

**Important:** After the fix, there must be **zero** bare CSS properties in Python scope.

### Also keep these constraints
- Don’t redesign the whole app. Keep existing UI/layout logic the same.
- Keep styling deterministic (no user-input HTML injection).
- If you see any `st.image(..., use_container_width=...)` deprecation warnings, update to the modern parameter style (e.g., `width="stretch"` or equivalent per Streamlit docs) while keeping behavior the same.
- If the app loads a logo from `assets/td_logo.png`, make it robust: if the file is missing or not a valid image, show a clean fallback (e.g., a “TD” badge) instead of crashing.

### Verification (must do)
Run these commands and ensure they pass:
- `python -m compileall app/ui/streamlit_app.py`
- `streamlit run app/ui/streamlit_app.py`

### Deliverable
- Provide the patch / code changes.
- Briefly explain what lines caused the `NameError`, and where the CSS now lives.
- Confirm the verification commands succeed.
