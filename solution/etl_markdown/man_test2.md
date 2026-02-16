---
name: text2sql-ui-td-and-pii-metadata-fix
description: >
  Fix the PII/metadata experience end-to-end: ensure PII questions route to Azure AI Search (metadata indexes),
  return user-friendly answers (no raw SQL/QueryResult dumps), and upgrade the Streamlit UI to a modern
  TD-like theme with an Activity Log event stream. Add backend tests first, then wire into frontend.
argument-hint: |
  You are in repo: text2sql_v2
  Run from repo root.
  Key files likely involved (adjust if paths differ):
    - app/main_cli.py
    - app/core/orchestrator.py (or router/orchestrator facade)
    - app/core/ai_search_service.py
    - app/ui/streamlit_app.py
    - app/ui/* (ui models/adapters)
  Existing Azure AI Search indexes in UI:
    - meta_data_field
    - meta_data_table
    - meta_data_relationship

tools:
  - terminal (pytest, streamlit run)
  - filesystem (read/write/search)
  - python (unit tests)
handsoffs:
  - label: optional-design-review
    agent: reviewer
    prompt: >
      Review the UI/CSS changes for maintainability and accessibility, and ensure debug-only details are not shown to end users.
    send: >
      Provide a short review + list of improvements (no code changes unless critical).
---

# Goal

When a user asks a PII/metadata question (e.g. “show me columns that have PII information”):
1) The system must route to **AI Search metadata** (NOT SQL execution).
2) It must return **user-friendly output** (e.g., a list/table of fields + short explanation), and **never** dump raw SQL or `QueryResult(...)` into the chat.
3) If no metadata is found, ask a **clarifying question** that helps the user succeed (e.g., “Do you mean fields marked Confidential?”).
4) The Streamlit UI must look **modern, TD-like (white/green)** and show:
   - Chat bubbles
   - Activity Log that streams events (debug-only)
   - A grid/table for metadata hits

**Important:** Implement and verify backend tests first. Then wire into Streamlit.

---

# A) Diagnose the current behavior (must do before coding)

From the screenshots:
- CLI logs show routing to `[ai_search]` with `Generated SQL: None` ✅ (routing is correct)
- Streamlit Activity Log still shows `llm generated SQL` + `sql_execute` for PII questions ❌ (frontend is calling a different code path or fallback logic is incorrect)
- AI Search is returning **0 hits** (or hits aren’t being parsed/mapped to output).

So we need to:
1) **Unify the entrypoint** used by CLI + Streamlit so behavior cannot diverge.
2) Make AI Search queries for PII **robust** (synonyms + index schema aware).
3) Ensure UI shows only `assistant_message` + optional metadata table, never raw objects.

---

# B) Data models (signatures must exist)

Create or extend models so the UI can render metadata results cleanly.

## 1) app/core/metadata_types.py (new)

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class MetadataHit:
    schema: Optional[str]
    table: Optional[str]
    column: Optional[str]
    business_name: Optional[str]
    description: Optional[str]
    data_type: Optional[str]
    security: Optional[str]          # e.g., Confidential / Public / Restricted
    source_index: str                # e.g., meta_data_field
    score: Optional[float] = None
```

## 2) Extend QueryResult (existing)

Wherever `QueryResult` lives (looks like `app/core/query_result.py`), ensure it has:

```python
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class QueryResult:
    sql: Optional[str] = None
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0
    columns: list[str] = field(default_factory=list)
    execution_ms: float = 0.0
    error: Optional[str] = None

    # user-facing
    assistant_message: str = ""

    # debug / trace
    events: list[Any] = field(default_factory=list)

    # NEW: metadata results (AI Search)
    metadata_hits: list["MetadataHit"] = field(default_factory=list)
    route: str = ""   # "sql" | "ai_search" | "clarify" | "smalltalk"
```

**Rules:**
- `assistant_message` must never be empty at the end of a turn.
- For PII/metadata route, `sql` must remain `None` and `rows` should remain empty.

---

# C) Unify backend entrypoint (critical best practice)

Create a single streaming entrypoint used by BOTH CLI and Streamlit.

## app/core/orchestrator_facade.py (new or refactor existing)

```python
from __future__ import annotations
from typing import Any, Callable, Iterator, Optional
from app.core.query_result import QueryResult

TraceCallback = Callable[[Any], None]

def run_turn(
    user_text: str,
    *,
    trace: Optional[TraceCallback] = None,
) -> QueryResult:
    ...
```

If you already have something similar, ensure BOTH:
- `app/main_cli.py` uses `run_turn(...)`
- `app/ui/streamlit_app.py` uses `run_turn(...)`

This removes the “CLI works but UI doesn’t” drift.

---

# D) Planner routing for PII/metadata (must be deterministic)

Wherever your planner logic lives (e.g., `planner_types.py` + `llm_router.py`):
- Add a deterministic keyword override BEFORE calling LLM planner:

PII/metadata trigger words:
- pii, personal data, confidential, sensitive, privacy, gdpr
- “columns that have PII”, “fields that are confidential”, “show sensitive fields”

Behavior:
- If triggers match → `route="ai_search"` and `search_index="meta_data_field"` (default) unless user specifies table.

Make sure this does NOT depend on the LLM planner for basic routing.

---

# E) AI Search query improvements (why you get 0 results)

Main reasons for 0 hits:
1) The index does not contain literal “PII” anywhere (common).
2) You are searching wrong fields (or field names differ).
3) You need `query_type="full"` for OR queries.
4) The index is empty or you’re hitting the wrong endpoint/index.

## 1) Add index schema inspection (debug-only)

In `app/core/ai_search_service.py` (or equivalent), add:

```python
def get_index_fields(index_name: str) -> list[str]:
    """Return field names for the index. Use SearchIndexClient."""
    ...
```

Log this to Activity Log when debug is enabled.

## 2) Build a robust PII search strategy

Add helper (signature must exist):

```python
def build_pii_search_text(user_text: str) -> str:
    """Return an AI Search query string that works even if 'PII' is not present."""
    ...
```

Recommended strategy:
- Use synonyms + common PII indicators:
  - confidential, restricted, personal, privacy
  - email, phone, address, name, dob, ssn, sin
- Prefer OR semantics via `query_type="full"`:
  - `pii OR confidential OR personal OR email OR phone OR address OR name`
- If results are 0, retry with broader query:
  - `confidential OR personal OR privacy`
- Also consider searching column/business_name/description/security fields specifically (if they exist):
  - `search_fields=["column","business_name","description","security"]` (only if those are actual fields)

## 3) Implement AI Search call

```python
from app.core.metadata_types import MetadataHit

def search_pii_metadata(
    query: str,
    *,
    index_name: str = "meta_data_field",
    top: int = 50,
) -> list[MetadataHit]:
    ...
```

Mapping rules (defensive):
- Use `.get()` for all fields
- If the index has a field `@search.score`, store it in `score`
- Always set `source_index=index_name`

If 0 hits:
- Return empty list (do not crash)
- Let orchestrator produce a clarifying `assistant_message`

---

# F) Orchestrator behavior for ai_search route (no SQL allowed)

In `run_turn()` logic:

1) emit event: `[planner] Received question`
2) if route == ai_search:
   - emit: `[ai_search] Searching metadata`
   - call `search_pii_metadata(...)`
   - emit: `[ai_search] Found N hits`

3) If hits exist:
   - Set `result.metadata_hits = hits`
   - Set `result.assistant_message` to a friendly summary, e.g.:

     “I found 12 fields that look sensitive/confidential. Here are the top 10.  
      Want me to filter to a specific table or show only ‘email/phone/address’ fields?”

   - Set `result.route = "ai_search"`
   - Return immediately (do NOT call SQL generator/sanitizer/executor).

4) If no hits:
   - Set `assistant_message` to a helpful clarification:

     “I couldn’t find fields explicitly labeled ‘PII’ in the metadata.  
      Do you want me to (1) list fields marked **Confidential**, or (2) search for common PII indicators like **email/phone/address**?”

   - route = "clarify"
   - Return immediately (no SQL).

Also add a guardrail:
- If route == ai_search, assert `result.sql is None` and skip all SQL steps.

---

# G) Backend tests (required before frontend)

Create tests that prove:
1) PII questions route to AI Search
2) No SQL is generated/executed for ai_search route
3) build_pii_search_text uses synonyms and OR logic
4) assistant_message is never empty

## 1) tests/test_pii_routes_to_ai_search.py

- Mock planner/router so the route becomes ai_search for “PII”
- Mock `search_pii_metadata` to return hits
- Assert:
  - `result.route == "ai_search"`
  - `result.sql is None`
  - `len(result.metadata_hits) > 0`
  - `result.assistant_message` contains a friendly summary

## 2) tests/test_pii_no_hits_clarify.py

- Mock `search_pii_metadata` to return []
- Assert:
  - `result.route in {"clarify","ai_search"}` (depending on your naming)
  - `assistant_message` asks a clarifying question
  - `sql is None`

## 3) tests/test_build_pii_search_text.py

- Input: “show me columns with PII information”
- Output must contain at least: `pii` and `confidential` and `email` (or your chosen list)
- If using OR logic, assert `OR` appears.

Run: `pytest -q` and ensure green.

---

# H) Streamlit UI upgrade (TD look + metadata grid + safe chat)

Update `app/ui/streamlit_app.py`:

## Rendering rules
- Chat bubble shows only:
  - user text
  - assistant_message
- If `metadata_hits` present:
  - render a table/grid (st.dataframe) with columns:
    `schema, table, column, security, business_name, description`
- Technical details (events, SQL, stack traces) go ONLY into Activity Log when Debug mode ON.
- Never print `QueryResult(...)` object in chat.

## TD styling
- White background
- TD green accents
- Rounded chat cards
- Sidebar for “Indexes” + Debug toggle

## Keyboard
- Use `st.chat_input()` (Enter to send)
- Optional: Shift+Enter for newline (if you add a text area toggle)

---

# I) Manual verification commands (Copilot must run and paste outputs)

Backend (must pass first):
1) `pytest -q`
2) `.venv/bin/python -m app.main_cli "show me the columns that have PII information"`

Frontend:
3) `.venv/bin/streamlit run app/ui/streamlit_app.py`
4) Ask: “show me the list of fields that have PII information”
   - Expected: friendly response + metadata table OR clarifying question
   - No SQL shown in chat
   - Activity Log shows ai_search steps (debug-only)

---

# Acceptance criteria

- PII questions NEVER trigger SQL generation/execution.
- AI Search query is robust (works even if the literal word “PII” isn’t present).
- If no metadata is found, the assistant asks a useful clarification question.
- Streamlit UI is TD-like and does not expose raw technical objects to end users.
- `pytest -q` passes.
