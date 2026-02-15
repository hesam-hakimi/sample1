COPILOT PROMPT — Step 1 (TD-themed UI shell + hook to existing orchestrator)

Goal
- Build a Streamlit UI with a TD-like look (white + TD green, clean “cards”, TD logo).
- UI must call the existing end-to-end pipeline (your Query Orchestrator) and display:
  1) the generated SQL
  2) the query result grid
  3) any errors in a user-friendly way
- Add an inline “Debug panel” section, but it must be DISABLED/HIDDEN unless DEBUG=true.

Constraints
- Do NOT change core logic unless required for the UI integration.
- Avoid new libraries unless necessary. If Streamlit is not allowed in this environment, stop and report the install error (don’t switch frameworks silently).
- Never print secrets from .env.

What to implement

A) Dependencies
1) Check if streamlit is available:
   - `python -c "import streamlit; print(streamlit.__version__)"`
2) If missing, add it to requirements.txt and install into the current venv:
   - Update requirements.txt (append `streamlit`)
   - Install: `pip install -r requirements.txt`
3) Re-run the import check above.

B) New files/folders
Create these files if they don’t exist:
1) `app/ui/__init__.py`
2) `app/ui/streamlit_app.py`
3) `.streamlit/config.toml`  (Streamlit theme file)
4) `assets/td_logo.png` (placeholder ok; if not available, UI should fall back to a text header “TD”)

C) Theme (TD-ish)
In `.streamlit/config.toml` set:
- base = "light"
- background = white
- primary color = TD green (use a constant in UI too so it’s easy to tweak)
- clean typography (default is fine)
Also inject small CSS in the app to create “card” containers:
- rounded corners, subtle border, padding
- do NOT over-style

D) UI behavior (Streamlit)
In `app/ui/streamlit_app.py` implement:
1) Header
   - TD logo (if file exists) + title (“Text2SQL”)
2) Main input card
   - Text area: user question
   - Button: “Run”
   - Optional controls (safe defaults):
     - Result limit (default 50, slider)
     - “Show SQL” toggle (on by default)
3) Results card
   - Show generated SQL (plain text, no markdown fences)
   - Show results in a grid (Streamlit dataframe/grid)
   - If result is empty: show the existing “0 rows fallback” message (whatever the orchestrator returns) and suggestions.
4) Error handling card
   - Catch exceptions and show:
     - Short error summary (1–2 lines)
     - A “Copy diagnostics” multi-line text block (ONLY when DEBUG=true) that includes:
       - exception type + message
       - stack trace
       - last generated SQL (if available)
       - model/deployment name (non-secret)
       - timestamps/timings (if available)

E) Integration point (IMPORTANT)
- Do NOT re-implement the pipeline in UI.
- Find the existing “single entry point” that the CLI uses (the code called by `python -m app.main_cli "question"`).
- Create ONE function that UI calls, for example:

  Function (add ONLY if missing):
  - `app/core/orchestrator_facade.py`
    - `def run_question(question: str, *, limit: int | None = None) -> QueryResult:`
    - This should call the same orchestrator used by CLI and return the same QueryResult structure (or a thin wrapper).
  - If QueryResult already exists, reuse it.

Required return structure (must be accessible to UI)
- QueryResult must provide (directly or via fields):
  - `sql: str`
  - `rows: list[dict] | pandas.DataFrame | None`
  - `row_count: int`
  - `warnings: list[str]` (for 0-rows suggestions)
  - `debug: dict` (optional; only populated/used when DEBUG=true)
  - `error: str | None` (optional; if you prefer not raising)

If the current code doesn’t expose these cleanly:
- Do the smallest refactor needed so BOTH CLI and Streamlit use the same “run_question” function.

F) Debug mode rules
- Read DEBUG from env/config (already exists in your project).
- If DEBUG != true:
  - Hide/disable the debug panel entirely.
  - Do not show stack traces.
- If DEBUG == true:
  - Show the inline debug panel (expander is fine).
  - Show “Copy diagnostics”.

G) Run commands (acceptance)
1) Start UI:
   - `streamlit run app/ui/streamlit_app.py`
2) Test query that returns rows:
   - “show me 10 rows from v_dlv_dep_prty_clr”
3) Test query that returns 0 rows to trigger fallback:
   - “show me the list of all clients who are based in usa”
4) Verify:
   - UI looks TD-ish (white + green, clean cards, logo/title)
   - No markdown fences in SQL
   - Results show in grid
   - Debug panel hidden when DEBUG is false
   - Debug panel appears when DEBUG=true

Output to paste back to me
- The terminal output of:
  1) the streamlit import/version check
  2) `streamlit run ...` startup logs
- A screenshot of the Streamlit page (main + results)
- If any error occurs, paste the full stack trace
