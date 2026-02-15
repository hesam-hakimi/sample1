## Prompt: Make the Streamlit UI look modern (TD-style: clean white + green), without breaking logic

You are in a Python Streamlit repo. The app works, but the UI looks plain/misaligned.  
Refactor **ONLY the UI layer** to look modern and polished (white background, TD-green accents), while keeping the existing SQL generation/execution logic unchanged.

### Target file(s)
- Primary: `app/ui/streamlit_app.py`
- You may add small UI helpers in `app/ui/` if needed (e.g., `ui_components.py`), but avoid big refactors.

---

## Requirements

### 1) Keep core behavior identical
- Do **not** change how the app:
  - reads config
  - calls the orchestrator/LLM
  - executes SQL
  - returns results
- Only improve layout, styling, and presentation.

### 2) Modern page layout (like a clean banking dashboard)
Implement:
- `st.set_page_config(page_title="Text2SQL", layout="wide")`
- A clean header area:
  - left: logo + app name + subtitle
  - right: small status pill (e.g., “Local Mode” / “Connected”)
- A main “query card” section:
  - Question input (full width)
  - Result limit slider + “Show SQL” toggle + Run button aligned nicely in one row
- A results section that feels “app-like”, not “notebook-like”.

### 3) Results presentation (must be better than current)
- Show results in **Tabs**:
  - **Results**: data grid
  - **SQL**: generated SQL in a code block
  - **Debug**: timing + row count + any debug output (if exists)
- Use `st.dataframe` for the grid, set a reasonable height and enable full width.
- If there are 0 rows, show a friendly message with suggestions (but do not change backend logic).

### 4) Styling rules (avoid previous CSS crash)
- All CSS must be injected via **ONE** function, called once:
  - `inject_css()` that uses `st.markdown("""<style>...</style>""", unsafe_allow_html=True)`
- There must be **zero** stray CSS lines in Python scope.
- Use a clean design:
  - white background
  - subtle borders
  - soft shadows
  - TD-like green accent for buttons/toggles/headers
- Don’t use external CDNs.

### 5) Logo robustness (no crashes)
- If `assets/td_logo.png` is missing/invalid, show a fallback “TD” badge (still green) and continue.

### 6) Streamlit compatibility cleanup
- Fix any Streamlit deprecation warnings (e.g. `use_container_width` changes) while keeping behavior identical.

---

## Acceptance Criteria (must pass)
1. `python -m compileall app/ui/streamlit_app.py` ✅
2. `streamlit run app/ui/streamlit_app.py` ✅ loads without errors
3. UI looks modern and aligned:
   - header is neat
   - query controls are aligned
   - results are in tabs
   - dataframe uses full width and has a good height

---

## Deliverable
- Provide a patch (diff) or the full updated `app/ui/streamlit_app.py` (and any small helper file if you created one).
- Explain briefly:
  - what UI sections were changed
  - where CSS is injected
  - how logo fallback works
