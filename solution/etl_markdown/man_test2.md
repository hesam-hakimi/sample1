---
name: Text2SQL UI Agent — User-Friendly Responses (Prompt Update)
description: >
  Update the backend agent + UI so end users get clear, non-technical answers.
  Hide internal SQL/latency/errors by default, but keep a developer-facing streamed log in the Activity Log panel.
argument-hint: >
  Copy/paste this into GitHub Copilot Chat. It instructs Copilot exactly what prompt changes to make.
tools: []
handoffs:
  - label: Backend-agent prompt update
    agent: github-copilot
    prompt: |
      CONTEXT
      - This repo has a Text2SQL chat UI (Streamlit) and a backend router/planner that can:
        1) decide whether to use AI Search (metadata) or other tools,
        2) generate SQL,
        3) sanitize SQL (remove markdown fences),
        4) execute SQL in SQLite,
        5) provide a fallback when result set is 0 rows.
      - We already have an event stream / activity log (planner → ai_search → prompt → llm → sql_sanitize → sql_execute → fallback, etc.)
      - Current problem: assistant responses still leak technical details (SQL timings, sanitization notes, “no rows fallback” technical phrasing).
      - Goal: user sees business-friendly answers; technical details only appear in Activity Log (developer view).

      WHAT TO CHANGE (PROMPTS ONLY, NO CODE UNLESS ASKED)
      1) Update the primary assistant prompt (and any planner/system prompts if present) to enforce:
         - User-facing messages MUST be non-technical by default.
         - Do NOT mention:
           * SQL statements
           * table/view names unless user asked “what tables exist?”
           * latency timings (ms)
           * sanitization / markdown fences / SDK versions / stack traces
           * internal tool names (“planner”, “sql_execute”, etc.)
         - The UI may still display Activity Log events separately; the assistant message must not include them.

      2) Define a strict RESPONSE CONTRACT (what the LLM should output) so the UI can render consistently.
         - The assistant MUST always produce:
           A) user_message: string (human-friendly)
           B) followups: list[string] (0–5 suggested next questions)
           C) needs_clarification: boolean
           D) clarification_questions: list[string] (0–3), only when needs_clarification=true
           E) safe_notes_for_logs: string (optional) — technical notes intended ONLY for Activity Log, not user chat

         - If your project already uses a JSON response_format:
           * keep it compatible with existing code
           * ensure keys above are present
           * keep additional keys allowed but not required

      3) Update behavior for common cases:

         CASE A — Smalltalk (“hi”, “hello”, “thanks”)
         - user_message: friendly + suggests examples.
         - followups: include 2–4 examples such as:
           “What tables are available?”
           “Show me 10 rows from <table>”
           “Count deposits by day”
         - Never query tools for smalltalk.

         CASE B — User asks “what tables are available?”
         - user_message: list table names in bullet form (OK to show names here).
         - Add 1–2 tips like “You can ask for a sample: ‘show me 10 rows from …’”.

         CASE C — Query returns results (N rows)
         - user_message should summarize results in plain language:
           - If N is small: show a compact table-like preview (top 10 rows), with friendly column labels if available.
           - If N is large: summarize + offer to filter / group / export.
         - Do NOT mention execution time.
         - Do NOT show raw SQL.

         CASE D — Query returns 0 rows
         - user_message must NOT say “0-row fallback” or “no results found” alone.
         - Instead:
           1) Briefly state no matching records were found for the requested filter.
           2) Offer 2–3 actionable refinements:
              - suggest alternative filter values discovered (e.g., “TERR_CD looks like state/province codes (NY, CA, …) rather than ‘US’”)
              - ask a clarification question if needed (e.g., “Do you mean US-based clients, or clients in a specific state?”)
           3) Provide followups that the user can click/type.

         CASE E — Errors (tool failure, SQL errors, missing env vars)
         - user_message: brief apology + one simple next step (retry / rephrase / check setup).
         - Put full technical detail in safe_notes_for_logs only.
         - needs_clarification should be false unless you truly need user input.

      4) Add STYLE RULES to the prompt
         - Use short paragraphs.
         - Prefer bullets for lists.
         - Never mention internal file paths.
         - Never expose secrets or env var values.
         - If you must mention a table name, format it consistently (backticks are OK), but avoid overusing.

      DELIVERABLES (NO CODE)
      - Produce the updated prompt text(s) as markdown blocks:
        1) “System/Assistant Prompt (User-Facing)”
        2) “Planner Prompt (Tool Decision) — if exists”
        3) “Response JSON Schema”
      - Also include a short checklist for manual testing (3–5 tests) that I will run after applying the prompt changes.

      ACCEPTANCE CRITERIA
      - “Deposit count by day?” produces a helpful clarification instead of technical details.
      - “What tables are available?” lists the 4 tables without SQL/latency.
      - “show me 10 rows from v_dlv_dep_prty_clr” shows a user-friendly preview (no SQL shown).
      - Any technical diagnostics appear ONLY in Activity Log / safe_notes_for_logs.

  - label: Frontend rendering alignment
    agent: github-copilot
    prompt: |
      CONTEXT
      - The UI shows chat bubbles + an Activity Log stream.
      - The agent will now return a structured response:
        user_message, followups, needs_clarification, clarification_questions, safe_notes_for_logs.

      TASK (NO CODE UNLESS ASKED)
      - Verify the UI uses ONLY user_message in the Assistant chat bubble.
      - Activity Log should display:
        - streamed events emitted by backend
        - safe_notes_for_logs (if present) as “developer note”
      - Followups should render as clickable chips/buttons (optional) or as a short list.
      - Clarification questions should be displayed as a small “I need one detail” section.

      ACCEPTANCE CRITERIA
      - Chat bubble never shows SQL, execution time, sanitization, or tool names.
      - Activity Log can show technical steps.

other info:
  - If you find an existing prompt file (e.g., app/prompts/*.md or similar), update it in-place.
  - If prompts are embedded in Python, extract them into a dedicated prompt file only if low-risk.
  - Keep changes minimal and testable; do not refactor unrelated parts.
