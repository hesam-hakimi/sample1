COPILOT PROMPT — Fix Streamlit crash on TD logo (PIL.UnidentifiedImageError)

Context
- Streamlit crashes at startup when rendering the logo.
- Error: `PIL.UnidentifiedImageError: cannot identify image file <_io.BytesIO object ...>`
- Failing line is in `app/ui/streamlit_app.py` around the `st.image(...)` call for `LOGO_PATH`.

Goal
- Streamlit must NEVER crash because of the logo.
- If the logo is missing/invalid/unreadable, show a clean text fallback (“TD”) and continue rendering the app.
- Keep TD theme (white + green). No secrets printed.

Step 1 — Validate the asset (do this in terminal)
1) Confirm the file exists and its size is not zero:
   - `ls -l assets/td_logo.png`
2) Identify file type:
   - `file assets/td_logo.png`
3) Quick PIL verification:
   - `python -c "from PIL import Image; p='assets/td_logo.png'; im=Image.open(p); im.verify(); print('OK')"`

If any command fails, assume the logo file is invalid.

Step 2 — Patch Streamlit to load logo safely (code change)
In `app/ui/streamlit_app.py`:

A) Add imports (if not present):
- `import io`
- `from PIL import Image, UnidentifiedImageError`

B) Create a helper function (new function) near the top:
- Name: `render_td_logo(logo_path: Path, width: int = 48) -> None`
- Behavior:
  1) If `logo_path` does not exist OR size is 0 → render fallback header:
     - `st.markdown("<div class='td-brand'>TD</div>", unsafe_allow_html=True)`
     - return
  2) Try to load with PIL and pass a PIL Image to Streamlit:
     - `img = Image.open(logo_path)`
     - `st.image(img, width=width)`
  3) Catch `(UnidentifiedImageError, OSError, ValueError)` and fallback to “TD” text (same as above) without raising.

C) Replace the direct `st.image(...)` call
- Wherever you currently call `st.image(str(LOGO_PATH), width=48)` (or similar), replace it with:
  - `render_td_logo(LOGO_PATH, width=48)`

D) Add minimal CSS for the fallback “TD” badge (inside your existing CSS block)
- Add a class `.td-brand` with:
  - TD green background
  - white text
  - padding + border radius
  - bold font
  - inline-block display

IMPORTANT
- Do NOT change any orchestrator/SQL logic in this step.
- Only fix logo rendering so the app starts reliably.

Step 3 — Re-run Streamlit (terminal)
- `/app1/tag5916/projects/text2sql_v2/.venv/bin/streamlit run app/ui/streamlit_app.py`

Acceptance Criteria
- Streamlit starts without crashing even if `assets/td_logo.png` is invalid.
- Header shows either the image OR the “TD” badge.
- App loads to the point where the main input card is visible.

Output to paste back to me
- The results of:
  - `ls -l assets/td_logo.png`
  - `file assets/td_logo.png`
  - the PIL verify command output (OK or error)
- The Streamlit startup output (first ~30 lines)
- A screenshot of the running UI header (logo or TD badge)
