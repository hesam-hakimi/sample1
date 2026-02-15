You are working in a Python Streamlit app.

Problem:
When running `streamlit run app/ui/streamlit_app.py`, the app crashes with:
NameError: name 'display' is not defined
Traceback points to app/ui/streamlit_app.py around line ~90 where the file contains a raw CSS line like:
display: inline-block;

Root cause:
A CSS property line was accidentally inserted into Python code as a standalone statement. All CSS must be inside a string passed to st.markdown(..., unsafe_allow_html=True).

Task:
1) Open and edit `app/ui/streamlit_app.py`.
2) Find any standalone CSS lines (e.g. `display: ...;`, `padding: ...;`, `background: ...;`, etc.) that exist outside a Python string.
3) Move ALL CSS into ONE single `st.markdown("""<style> ... </style>""", unsafe_allow_html=True)` block near the top of the file (after imports).
4) Ensure no stray CSS property lines remain anywhere in Python scope.
5) Do not break the app layout. Keep the existing UI behavior.
6) Add a small helper `inject_css()` function that is called once, so CSS is injected cleanly.
7) After the change, run:
   - `python -m compileall app/ui/streamlit_app.py`
   - `streamlit run app/ui/streamlit_app.py`
   and confirm the app starts with no NameError.

Output:
- Provide the final patched `app/ui/streamlit_app.py` (full file content or a clean diff).
- Include the exact commands used for verification and their result.

Constraints:
- Do not introduce new dependencies.
- Keep all styling inside the single style block.
