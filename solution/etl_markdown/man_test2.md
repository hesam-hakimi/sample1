---
name: text2sql-pii-metadata-routing
description: |
  Fix “PII questions return no results” by routing PII/security/metadata questions to Azure AI Search (metadata index),
  returning user-friendly answers + a grid, and adding backend tests to prevent regressions.
argument-hint: |
  Optional (helps accuracy): include a table/view name.
  Examples:
  - "PII columns in v_dlv_dep_prty_clr"
  - "Which columns are confidential in v_dlv_dep_tran?"
tools:
  - repo:edit-files
  - repo:terminal
  - python
handoffs:
  - label: implement
    agent: developer
    prompt: |
      You are implementing the backend fix for PII/security/metadata questions in the Text2SQL project.

      Context / Problem
      - When the user asks: "show me the columns that have PII information", the system currently returns "No results found".
      - A debug screenshot shows the AI Search tool *did* find metadata rows (Security = 'Confidential'), but the code then
        converted those rows into a synthetic SQL statement using reserved identifiers like `Table`, causing SQLite to error
        (`near "Table": syntax error`). That error is later surfaced as "No results found".

      Goal
      - PII/security/metadata questions MUST:
        1) call Azure AI Search (metadata index)
        2) return a user-friendly answer (no raw QueryResult repr, no stack traces)
        3) optionally show a results grid (rows), but DO NOT try to execute synthetic SQL in SQLite.

      Key Behavior Rules (tool routing)
      - Treat these as metadata_lookup (AI Search FIRST; do not run SQL unless user explicitly asks to query data values):
        * pii, personal info, sensitive, confidential, security classification
        * “what does column X mean”, “definition of …”, “business meaning”
        * “which columns”, “data dictionary”, “column descriptions”, “schema metadata”
      - Treat these as sql_query (SQLite):
        * aggregations, counts, sums, group by, trends, “by day”, “top N”, “filter where…”
      - If ambiguous (no table mentioned and the result set would be huge), ask a clarifying question.

      REQUIRED Code Changes (do not skip)
      1) Planner decision schema: add/confirm an explicit metadata intent.
         - Update the planner output model to include:
           - intent: Literal["sql_query","metadata_lookup","smalltalk","clarify"]
           - needs_ai_search: bool
           - needs_sqlite: bool
           - clarifying_questions: list[str]
           - user_facing_summary: str (short)
         - Ensure the planner sets:
           - intent="metadata_lookup", needs_ai_search=true, needs_sqlite=false
           for “PII/security/metadata” queries.

         Suggested signature:
         ```py
         # app/core/planner_types.py (or similar)
         from dataclasses import dataclass
         from typing import Literal

         @dataclass
         class PlannerDecision:
             intent: Literal["sql_query","metadata_lookup","smalltalk","clarify"]
             needs_ai_search: bool
             needs_sqlite: bool
             clarifying_questions: list[str]
             user_facing_summary: str
         ```
         If you already use Pydantic/BaseModel, keep style consistent.

      2) AI Search results MUST NOT be converted into SQL for SQLite execution.
         - Implement a dedicated handler that returns QueryResult with rows/columns populated.
         - Keep QueryResult.sql=None (or a short string like "-- metadata lookup via AI Search") for this path.

         Required signatures (adjust filenames to your repo, keep semantics):
         ```py
         # app/core/ai_search_service.py
         class AISearchService:
             def search_metadata(self, query: str, *, top_k: int = 20) -> list[dict]:
                 ...
         ```

         ```py
         # app/core/orchestrator.py (or wherever routing occurs)
         class Orchestrator:
             def handle_metadata_lookup(self, user_text: str) -> "QueryResult":
                 ...
         ```

      3) User-friendly response formatting (metadata results)
         - If results found:
           - Provide a short summary (1–3 sentences).
           - Group results by table/view.
           - Show up to top 30 rows (or top_k).
           - Include: schema, table/view, column, security label, short description.
         - If no results found:
           - Ask 1 clarifying question such as:
             "Do you want PII/confidential columns across all tables, or for a specific table/view (e.g., v_dlv_dep_prty_clr)?"

      4) Safety / UX
         - Do NOT show raw QueryResult(sql=..., rows=...) in user chat.
         - Only show technical details behind a debug flag (DEBUG=true), and even then in a separate channel/section.

      5) Fix the existing failing synthetic-SQL approach (if still used anywhere)
         - If you must keep any synthetic SQL generation for internal debug, rename reserved identifiers:
           use schema_name, table_name, column_name instead of Schema/Table/Column.
           But the preferred fix is: do not execute synthetic SQL at all.

      Implementation checklist
      - Update planner prompt + decision parsing.
      - Update orchestrator routing:
        - metadata_lookup => ai_search_service.search_metadata() => QueryResult(rows=..., columns=..., assistant_message=...)
        - sql_query => existing SQL flow
      - Ensure errors from AI Search are surfaced as friendly messages:
        "I couldn't reach the metadata service right now. Please try again."

      Verification (run locally)
      - CLI:
        `.venv/bin/python -m app.main_cli "show me the columns that have PII information"`
        Expected: assistant returns a list/table of confidential columns (NOT “No results found”).
      - Also test:
        `.venv/bin/python -m app.main_cli "PII columns in v_dlv_dep_prty_clr"`
        Expected: focused list for that table/view.

  - label: test
    agent: unit-tester
    prompt: |
      Add backend tests to lock in the PII/metadata routing behavior.

      Add/Update Tests (pytest)
      1) Planner intent classification
         - Input: "show me the columns that have PII information"
         - Expected: decision.intent == "metadata_lookup"
                     decision.needs_ai_search is True
                     decision.needs_sqlite is False

      2) Orchestrator metadata path does NOT execute SQLite
         - Use a fake/mocked AISearchService returning sample metadata rows, e.g.:
           [{"schema":"aczrrdw","table":"v_dlv_dep_prty_clr","column":"CUST_EMAIL_ADDR","security":"Confidential","description":"Customer Email Address"}]
         - Assert:
           - QueryResult.rows is not empty
           - QueryResult.error is None/"" (no SQLite syntax error)
           - QueryResult.sql is None OR begins with "-- metadata lookup"
           - The SQL execution function was NOT called (mock/spies)

      3) Empty AI Search result => clarifying question
         - AISearchService returns []
         - assistant_message asks for a specific table/view OR clarifies scope.

      4) Regression test: reserved identifier bug
         - Ensure the metadata path never builds SQL that contains `SELECT ... Table ...` executed against SQLite.
         - (If you keep debug SQL, it must not be executed.)

      Commands
      - `.venv/bin/pytest -q`

      Acceptance criteria
      - All tests pass.
      - PII question triggers AI Search and returns a helpful answer.
      - No raw QueryResult repr leaks into user-facing messages.

---

# Extra notes for Copilot (do not ignore)

## What “PII” means in this project
- Your metadata index uses a `Security` label (e.g., `Confidential`).
- For the purpose of this UI, treat “PII columns” as:
  - Security == Confidential
  - OR description/business name contains common PII cues (email, phone, address, name, SIN/SSN, DOB, etc.)
  - Prefer returning what you have (don’t guess unseen PII).

## UI follow-up (later)
- Once backend is fixed, the Streamlit UI should display:
  - a clean assistant message (no technical fields)
  - a grid/table of the metadata rows
  - optional “Show technical details” expander when DEBUG=true
