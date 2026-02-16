---
name: Fix PII/Metadata AI Search results (backend + tests)
description: |
  Fix the backend so questions like "which fields have PII information" return REAL results from Azure AI Search
  (meta_data_field index), instead of returning "No results found". Add robust tests so this never regresses.
argument-hint: |
  Run this as a single Copilot task in the repo root. You must inspect the current code and indexes in config.
  Do NOT change UI yet; fix backend first, verify via CLI, then we will wire to Streamlit.
tools: ["Repo file search/edit", "pytest", "python -m app.main_cli"]
handsoffs:
  - label: "If blocked by Azure AI Search creds"
    agent: "User"
    prompt: "Ask me for the missing env vars (endpoint/index/key or MSI settings) and show the exact error."
    send: "Only if you cannot run a smoke query without credentials."
---

# Context / Problem

## Current behavior
- CLI routes PII questions to `ai_search`, but the final answer is still: **no PII columns found** (even though we have test/sample metadata).
- UI sometimes still runs SQL/fallback for PII questions (we will fix UI later), but **first** backend must reliably return metadata hits.

## Expected behavior
For user questions like:
- “show me the columns that have PII information”
- “which fields are confidential / sensitive / personal data”
- “PII fields in v_dlv_dep_prty_clr”
the app should:
1) route to **AI Search metadata** (NOT SQL),
2) query the correct index (default: `meta_data_field`),
3) return a **user-friendly list** of matching fields (table + column + business name + security/classification),
4) ask a clarifying question only when necessary (e.g., user asked “PII fields” but wants a specific table).

## Acceptance Criteria
- ✅ CLI: `python -m app.main_cli "show me the columns that have PII information"` returns a list (not "no results") **when metadata exists**.
- ✅ If metadata truly doesn’t exist, assistant asks a friendly clarification (scope/table) without crashing.
- ✅ No SQL is generated/executed for metadata/PII requests (and `QueryResult.sql` may be `None`).
- ✅ New tests cover:
  - metadata route chosen,
  - AI search query builder behavior (PII synonyms),
  - result parsing,
  - user-friendly response formatting,
  - no “re.search(None)” / TypeErrors when `sql is None`,
  - error-handling when AI Search returns 0 hits or raises.
- ✅ Existing behavior for SQL questions remains unchanged.

---

# Step-by-step implementation plan

## Step 0 — Reproduce & capture
1) Run:
```bash
.venv/bin/python -m app.main_cli "show me the columns that have PII information"
```
2) Confirm from the **events** that planner chooses `ai_search` and that SQL is not executed.
3) If SQL is executed anyway, the routing is wrong (see Step 2).

Save the full CLI output in the PR description.

---

## Step 1 — Verify AI Search index + data is actually present
We must distinguish “code bug” vs “index empty”.

1) Locate config for AI Search:
- `AZURE_SEARCH_ENDPOINT`
- `AZURE_SEARCH_KEY` OR MSI configuration
- index names: `meta_data_field`, `meta_data_table`, `meta_data_relationship`

2) Add (or run) a small smoke helper **without changing app behavior**:
- File: `scripts/debug_ai_search_metadata.py`
- It should:
  - connect to the configured index (default `meta_data_field`)
  - run a very broad query (e.g., `search_text="*"`, `top=3`)
  - print the number of docs returned and one sample doc keys

Example skeleton (adjust to your SDK usage):
```py
def smoke_query(index_name: str) -> dict:
    # return {"index": index_name, "count": <int>, "sample_keys": [...]}  # no secrets printed
```

3) If the index is empty, we need a seeding path (Step 1B).

### Step 1B — If index is empty: create a seeder (dev-only)
Create:
- `scripts/seed_meta_data_field_from_sqlite.py`

Behavior:
- read from local sqlite metadata sources if available, OR accept a small hardcoded list (safe demo)
- upload docs into `meta_data_field`
- deterministic doc IDs
- include fields needed for search: `schema`, `table`, `column`, `business_name`, `description`, `security` (or `classification`), plus an aggregated `content` field for full-text search

This is dev/demo-only. Guard with an explicit flag/env var:
- `ALLOW_AI_SEARCH_SEED=1`

Add README snippet in script header.

---

## Step 2 — Fix routing: metadata/PII must be AI-search-only
Where to look (expected):
- `app/core/planner*.py` (or similar) — plan classification
- `app/core/orchestrator*.py` — executes plan steps
- `app/main_cli.py` — prints events + final answer

Goal:
- Introduce an explicit plan type:
  - `plan.intent = "metadata"` (or `task_type="metadata_lookup"`)
  - `plan.tool = "ai_search"`
  - `plan.sql_required = False`

### Required signatures (adjust names to your repo)
Add/update in `planner_types.py`:
```py
from dataclasses import dataclass
from typing import Literal, Optional

@dataclass
class Plan:
    intent: Literal["sql", "metadata", "chitchat", "help"]
    requires_sql: bool
    requires_ai_search: bool
    metadata_query: Optional["MetadataQuery"] = None
```

Add/update a `MetadataQuery`:
```py
from dataclasses import dataclass
from typing import Literal, Optional

@dataclass
class MetadataQuery:
    scope: Literal["all", "table"]
    table: Optional[str]
    tags: list[str]  # e.g. ["pii", "confidential"]
    raw_user_question: str
```

In orchestrator:
- If `intent == "metadata"`:
  - call AI Search
  - **do not** call LLM-to-SQL or sqlite execute
  - format response for user
  - return `QueryResult(sql=None, rows=[], ...)` or a `MetadataResult` (preferred)

---

## Step 3 — Fix AI Search query building for “PII”
Most likely root cause: search uses a literal `"pii"` term but your metadata uses values like `"Confidential"` and business names like `"Customer Email Address"`.

Implement a query builder that expands synonyms.

### Create a single source of truth
File: `app/core/metadata_query_builder.py`

Signature:
```py
def build_pii_metadata_search(user_text: str) -> dict:
    """Returns a dict with search_text, filters, fields, top."""
```

Rules:
- If user mentions PII/sensitive/confidential/personal:
  - include synonyms and common PII tokens in `search_text`:
    - `pii OR "personal data" OR confidential OR sensitive OR email OR address OR phone OR name`
- Prefer filtering by classification if field exists:
  - `security eq 'Confidential'` OR `classification eq 'Confidential'`
  - but only if the index schema supports that field (see Step 1 smoke doc keys)
- If user names a table (exact or fuzzy), add a filter:
  - `table eq 'v_dlv_dep_prty_clr'`

Also add **fallback strategy**:
1) try vector/semantic (if implemented)
2) else try full-text on `content`
3) else try `search_text="*"` with filter by security/confidential

Return top 50.

---

## Step 4 — Parse hits and return user-friendly answer
Define a dataclass:
File: `app/core/metadata_types.py`
```py
from dataclasses import dataclass
from typing import Optional

@dataclass
class MetadataHit:
    schema: Optional[str]
    table: Optional[str]
    column: Optional[str]
    business_name: Optional[str]
    description: Optional[str]
    security: Optional[str]
    score: Optional[float] = None
```

AI search service signature:
File: `app/core/ai_search_service.py`
```py
class AiSearchService:
    def search_metadata_fields(self, q: MetadataQuery) -> list[MetadataHit]:
        ...
```

Response formatting:
File: `app/core/metadata_presenter.py`
```py
def format_pii_metadata_answer(hits: list[MetadataHit], q: MetadataQuery) -> str:
    """User-facing only. No SQL. No internal tool names."""
```

Output rules (IMPORTANT):
- If hits exist: show the top 10–20 as a readable list:
  - `• <table>.<column> — <business_name> (Security: Confidential)`
- If too many: group by table and show counts.
- If no hits: ask a clarification question:
  - “Do you want me to search across all tables, or a specific table/view?”
- Never leak internal exceptions or raw SDK errors to the user.

---

## Step 5 — Fix the specific crash: regex on None SQL
The screenshot shows `TypeError: expected string or bytes-like object, got 'NoneType'` where code does `re.search(..., t.sql, ...)`.

Where to fix:
- `app/main_cli.py` or wherever fallback tries to parse `QueryResult.sql`

Rule:
- Any post-processing that parses SQL must guard:
  - `if not query_result.sql: return ...` (skip SQL-based heuristics)

Add a regression test.

---

# Tests (pytest)

Create/extend:
- `tests/test_metadata_routing.py`
- `tests/test_ai_search_metadata.py`
- `tests/test_no_sql_for_metadata.py`

## Testing approach
- Do NOT call real Azure AI Search in unit tests.
- Mock the AI search client/service layer.
- Provide a deterministic “hit list” including examples like:
  - `v_dlv_dep_prty_clr.CUST_EMAIL_ADDR` (Confidential)
  - `v_dlv_dep_prty_clr.PRIM_NM_1` (Confidential)

## Must-have tests
1) Planner routes PII question → `intent="metadata"`, `requires_ai_search=True`, `requires_sql=False`
2) Orchestrator for metadata:
   - calls `AiSearchService.search_metadata_fields`
   - returns assistant message containing the field list
   - does NOT call sql generator or sqlite executor
3) If `AiSearchService` returns empty:
   - assistant asks clarification
   - no crash
4) Regression: `QueryResult.sql=None` does not break fallback/regex code

---

# Verification commands
After changes:
```bash
pytest -q
.venv/bin/python -m app.main_cli "show me the columns that have PII information"
.venv/bin/python -m app.main_cli "show me the columns that have PII information in v_dlv_dep_prty_clr"
```

Expected:
- PII questions → metadata answer (list), no SQL printed, no sqlite execution.
- SQL questions still work.

---

# Notes / Guardrails
- Keep logs/events for developer mode, but user-facing answer must be friendly and non-technical.
- Keep changes small and isolated: query builder + presenter + routing + tests.
- No UI changes in this step.
