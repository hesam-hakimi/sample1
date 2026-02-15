COPILOT PROMPT — Step: Apply TD Theme + Clean Layout + Debug Panel Gating (NO backend logic changes)

Context
- Streamlit UI works (query runs and shows results in a grid).
- We want TD look & feel: white + TD green, clean cards, simple header with TD logo/badge.
- Requirement: “inline panel” (debug panel) must be DISABLED/HIDDEN unless running in debug mode.
- Do NOT change SQL/Orchestrator/LLM logic in this step. UI-only refactor.

Target Files
- app/ui/streamlit_app.py (main)
- (Optional) app/ui/ui_theme.py (if you want to keep CSS/constants clean)
- assets/td_logo.png (already exists; use safe render function if present)

Step A — Add TD Theme (CSS injection)
1) In streamlit_app.py, create a small UI theme function:
   - Function name: apply_td_theme()
   - It injects CSS via st.markdown(..., unsafe_allow_html=True)
2) CSS goals:
   - Background: white
   - Primary: TD green (#008a00 or close)
   - “Card” containers: white card, subtle border, rounded corners, padding
   - Buttons: green background, white text, rounded
   - Reduce clutter: consistent spacing
   - Make the dataframe look like “clean grid” (container_width=True, a sensible height)

Step B — Header Bar
1) Add a top header bar:
   - Left: TD logo (or TD badge fallback) + title “Text-to-SQL”
   - Right: small status text (e.g., “Connected: SQLite”)
2) If you already have a safe logo renderer, reuse it. If not:
   - Make logo rendering fail-safe: never crash if the image is missing/invalid.
   - If logo fails, show a small “TD” badge instead.

Step C — Layout the main UI into clean “cards”
Build 3 sections:
1) Query Card
   - Text input (question)
   - Result limit slider (default from env/config; currently 50)
   - “Show SQL” checkbox
   - Run button aligned to the right
2) Results Card
   - If Show SQL checked: show generated SQL in a code block (no markdown fences inside SQL)
   - Show results in st.dataframe / st.data_editor (read-only) as a grid
3) Debug/Inline Panel (MUST be gated)
   - Only render this section if DEBUG==true (read from config/env)
   - Put it inside an expander (collapsed by default)
   - Contents: timings, retries, raw LLM snippet (truncated), errors/trace if any

Step D — Debug gating rules (important)
- Add a boolean: is_debug = config.DEBUG (or env DEBUG)
- If is_debug is False:
  - DO NOT show the Debug panel at all
  - Errors shown to user must be short and friendly (no stack trace)
- If is_debug is True:
  - Show detailed diagnostics inside the Debug panel only

Step E — Quick smoke test
1) Run with DEBUG=true and confirm Debug panel exists
2) Run with DEBUG=false and confirm Debug panel is hidden
3) Take a screenshot of:
   - Header + query card + results grid (TD themed)
   - Debug panel visible only in DEBUG=true

Acceptance Criteria
- UI has TD look: white background, green accents, clean cards, consistent spacing
- Results still show in a grid
- Debug/inline panel is visible ONLY when DEBUG=true
- No backend/orchestrator logic changes in this step

Output to paste back to me
- Which files changed + a screenshot of the new UI
- Confirm DEBUG=false hides the debug panel
