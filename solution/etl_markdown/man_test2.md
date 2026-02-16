---
name: Text2SQL - Fix PII/Metadata AI Search Flow (no “no results” false negatives)
description: >
  Update backend + tests so PII/metadata questions correctly use Azure AI Search and return user-friendly results.
  Prevent AI-search metadata hits from being (incorrectly) executed as SQL (reserved keyword “Table” bug),
  and ensure the UI renders only the friendly assistant message (not the raw QueryResult object).
argument-hint: >
  Run this in the repo root. Use the existing venv at .venv/ and current project layout (app/, scripts/, tests/).
tools: []
handoffs:
  - label: implement
    agent: github-copilot
    prompt: |
      CONTEXT
      - The CLI works for SQL questions, and we recently added an event stream and “0 rows fallback”.
      - For PII/metadata questions, the planner routes to AI Search (event: [ai_search] AI Search for metadata).
      - In Streamlit UI, asking “show me the columns that have PII information” shows “No results found”.
      - Debug output shows a QueryResult with:
          error='near "Table": syntax error'
          sql='SELECT ... Schema, Table, Column, ... FROM (SELECT ... UNION ALL ...)'
        This is a false-negative: AI Search likely returned hits, but we tried to post-process them by generating SQL
        with an alias named Table (reserved keyword), then executed it in SQLite. That fails, and the UI ends up
        showing “No results found” (and sometimes prints the raw QueryResult object).

      GOAL
      1) When the question is metadata/PII-related, we should query Azure AI Search and return a friendly answer
         WITHOUT running any SQL in SQLite.
      2) If we DO need SQL post-processing, never use reserved keywords (Table, Column, etc.) unquoted.
         Prefer renaming to table_name/column_name or quoting identifiers.
      3) Add backend tests to prevent regressions.
      4) (Optional but recommended) Update Streamlit UI to display only the assistant message + a clean table of
         metadata hits, and keep technical info only in the Activity Log.

      ACCEPTANCE CRITERIA
      - Running:
          .venv/bin/python -m app.main_cli "show me the columns that have PII information"
        does NOT crash and does NOT execute sqlite SQL (Generated SQL should be None).
      - Activity/events show: planner -> ai_search -> (no sql_execute)
      - The final answer is user-friendly and offers clarification if needed (scope: all tables vs specific table).
      - If AI Search returns hits, show a short list (top N) and optionally an expandable “details” section.
      - Unit tests cover:
        - PII/metadata routing uses AI Search path
        - No SQL is generated/executed for metadata responses
        - Reserved keyword bug is impossible (Table alias not used)
        - UI render helper (if added) doesn’t print raw QueryResult()

      IMPLEMENTATION PLAN (DO THIS STEP-BY-STEP, COMMIT-SIZED CHANGES)
      A) Define a clean response model for metadata hits
         - Create dataclass(es) in app/core/metadata_types.py:

           from dataclasses import dataclass
           from typing import Optional

           @dataclass(frozen=True)
           class MetadataHit:
               schema_name: Optional[str]
               table_name: Optional[str]
               column_name: Optional[str]
               business_name: Optional[str]
               description: Optional[str]
               data_type: Optional[str]
               security: Optional[str]
               score: Optional[float] = None

         - If you already have QueryResult, extend it safely (backwards-compatible):
           - Add: route: str (e.g., "sql" | "ai_search" | "clarify" | "smalltalk")
           - Add: metadata_hits: list[MetadataHit] | None = None
           - Ensure __repr__ is not used for UI display (UI must use assistant_message)

      B) Fix the AI Search path so it never runs SQL
         - Identify the function that handles tool results for AI Search metadata.
           It currently appears to build a SQL string like:
             SELECT Schema, Table, Column, ... FROM (SELECT 'x' AS Schema, 'y' AS Table, ...)
           and then executes it against SQLite. REMOVE this behavior.
         - Instead:
           - The AI Search tool/service returns a list[MetadataHit]
           - The orchestrator/planner returns QueryResult with:
             route="ai_search"
             sql=None
             rows=[] or None
             metadata_hits=[...]
             assistant_message=<friendly summary>
             error=None

         - Friendly summary rules:
           - If hits exist: “I found X columns marked Confidential or likely PII. Here are the top 10…”
           - If no hits: ask a clarifying question:
               “Do you mean PII/confidential columns across all tables, or in a specific table/view?”
             and suggest examples:
               “Try: ‘PII columns in v_dlv_dep_prty_clr’” / “email address columns” / “address columns”.

      C) Add a safe query expansion for PII intents (to increase recall)
         - In the AI-search query builder (planner or ai_search tool), when intent is PII/metadata:
           - Expand query terms:
             ["pii", "personal", "confidential", "sensitive", "email", "address", "phone", "name"]
           - Use OR semantics in the search text (or run a couple of searches and merge results).
         - Keep it deterministic: do not require LLM for expansion.

      D) Add tests (pytest)
         Create/extend tests in tests/ (use existing pattern):
         1) test_metadata_path_does_not_generate_sql
            - Mock AISearchService to return 2 MetadataHit objects.
            - Run orchestrator/router for question “show me the columns that have PII information”.
            - Assert result.route == "ai_search"
            - Assert result.sql is None
            - Assert result.metadata_hits length == 2
            - Assert no call to SqlService.execute_sql happened (mock/spy)
         2) test_metadata_no_hits_prompts_clarification
            - AISearchService returns []
            - Assert assistant_message includes a clarifying question (all tables vs specific table)
         3) test_reserved_keywords_never_used
            - Ensure any helper that formats metadata output never generates SQL with alias “Table”.
              (If you removed SQL generation entirely, assert the helper is absent or returns None.)

      E) Optional: Streamlit UI cleanup
         File: app/ui/streamlit_app.py (or equivalent)
         - When you receive QueryResult:
           - Append assistant_message to chat.
           - If metadata_hits is present, render a table/grid using st.dataframe with columns:
             schema_name, table_name, column_name, security, business_name
           - Do NOT render `QueryResult(...)` object directly.
           - Keep technical fields (sql, error, events) in the Activity Log panel only.

      VERIFICATION COMMANDS
      - Run unit tests:
          .venv/bin/pytest -q
      - Run CLI:
          .venv/bin/python -m app.main_cli "show me the columns that have PII information"
          .venv/bin/python -m app.main_cli "pii columns in v_dlv_dep_prty_clr"
      - Run Streamlit (if UI changes included):
          .venv/bin/streamlit run app/ui/streamlit_app.py

      NOTES / GUARDRAILS
      - Do NOT print raw SQL or stack traces in the user chat area.
      - If AI Search is unavailable/misconfigured, show a friendly message:
          “I can’t access metadata right now. Please check configuration and try again.”
        Log the technical error only in Activity Log.
      - Keep changes minimal and reversible (small commits).

      DELIVERABLES
      - Updated backend code (router/orchestrator + ai_search service) implementing the no-SQL metadata flow.
      - Tests proving the metadata path never executes SQLite SQL.
      - (Optional) Updated Streamlit UI rendering for metadata hits.
    send: |
      After changes, paste:
      - `pytest -q` output
      - CLI output for the two commands in VERIFICATION COMMANDS
      - A screenshot or text snippet showing the Streamlit response for the PII question (if UI updated)
---
# Extra: Quick diagnosis checklist (if AI Search still returns empty)
- Confirm index name used by code matches the populated index (e.g., `texttosql` vs `metadata`).
- Validate index has documents:
  - Search `confidential` and `email` and confirm at least 1 hit.
- Confirm fields are *searchable* in the index (Security/Description/BusinessName).
- Confirm the app is reading the correct env vars in `.env` (SEARCH_ENDPOINT, etc.).
