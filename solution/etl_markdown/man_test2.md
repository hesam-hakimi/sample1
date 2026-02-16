---
name: Text2SQL – Fix PII/Metadata AI Search Results (Backend-first) + Tests
description: >
  Debug and fix why PII/metadata questions return “No results” even though Azure AI Search `meta_data_field` index
  contains PII rows. Ensure backend routes PII/metadata questions to AI Search (NOT SQL), uses correct filters, and
  returns user-friendly answers. Add automated tests and a CLI debug command to validate the fix before touching UI.
argument-hint: |
  Run from repo root (text2sql_v2):
  - PII question example: "show me the columns that have PII information"
  - PII scoped example: "show me PII columns for v_dlv_dep_prty_clr"
tools:
  - python (3.11)
  - pytest
  - azure-search-documents (SDK already used in repo)
  - Azure AI Search (existing service/indexes)
handoffs:
  - label: Verification
    agent: Unit Tester
    prompt: |
      Run pytest and CLI verification steps. Confirm:
      1) PII/metadata questions call AI Search and never call SQL generation/execution.
      2) AI Search returns >= 1 results for seeded PII data.
      3) Final answer is user-friendly (no raw SQL / stack traces).
    send: |
      Provide console output snippets for:
      - pytest -q
      - python -m app.main_cli "show me the columns that have PII information"
      - python -m app.main_cli "show me PII columns for v_dlv_dep_agmt_clr"
---

## Context (what we’re seeing)

### Symptom
- User asks in CLI or UI: **“show me the columns that have PII information”**
- Activity log shows `[ai_search] Search metadata`, but assistant returns **“No results found”**
- Sometimes there was a crash like:
  - `TypeError: ... <lambda>() got an unexpected keyword argument 'filter'`
- In UI, the activity log may still show SQL steps (`prompt`, `llm`, `sql_sanitize`, `sql_execute`) even for metadata/PII questions.

### Why this happens (most likely)
One or more of these are true:

1) **Search implementation / mock doesn’t accept `filter=`**
   - Your `AISearchService.search_metadata(..., filter=...)` passes keyword args to `search_impl`.
   - If `search_impl` is a lambda like `lambda q, top_k: ...`, it will crash when `filter=` is passed.
   - If the error is swallowed, it may look like “0 results”.

2) **Filter field name/value mismatch**
   - In Excel, `PII` values are `"Yes"/"No"` (strings).
   - In Azure AI Search index, the field might be `pii` (lowercase), or boolean, or not filterable.
   - If your query builder uses `PII eq true` but indexed values are `"Yes"`, you’ll get 0 hits.
   - If your code filters on `PII` but the index field is `pii`, you’ll get 0 hits.

3) **You’re doing full-text search instead of a structured filter**
   - “PII columns” is typically “return rows where PII == Yes”.
   - A full-text query like `search_text="PII"` might return nothing if the term doesn’t exist in searchable fields.

4) **Orchestrator falls back to SQL path on 0 hits**
   - For metadata questions, 0 hits should produce a clarifying question or “no metadata found” message.
   - It should **not** generate SQL or run SQL fallback.

---

## Acceptance Criteria

1) For metadata/PII questions:
   - Route is **AI Search only**.
   - **No SQL** is generated or executed.
   - Events show: `planner -> ai_search -> (present_metadata)` and stop.

2) If metadata exists:
   - Return user-friendly results (table-like list) with **table + column + classification**.
   - If user did not specify a table, return top N across all, and ask if they want to narrow.

3) If metadata does not exist:
   - Ask clarifying question (scope/table) and offer examples.

4) Add tests:
   - Unit test verifies query builder produces the correct `filter` and `search_text`.
   - Unit/integration-ish test verifies orchestrator uses AI Search and returns results when search service returns hits.
   - Unit test verifies orchestrator does **not** call SQL pipeline for metadata questions.

5) Add a debug command/script:
   - Quickly prints index schema field names + a sample query result, so we can confirm mismatch (PII vs pii, Yes vs true).

---

## Step-by-step tasks

### Step 0 — Identify index schema and field names (very important)
Add a small helper (or reuse existing code) to fetch index schema:
- Use `SearchIndexClient.get_index(index_name)` and print:
  - field name
  - type
  - `searchable`, `filterable`, `facetable`

**Create**: `scripts/debug_ai_search_index.py`
- Inputs: `--index meta_data_field`
- Outputs: list of fields and key properties

Also add `scripts/debug_ai_search_query.py`
- Inputs: `--index meta_data_field --search "*" --filter "pii eq 'Yes'" --top 5`
- Prints first rows and which fields are present

> This step tells us whether the correct filter should be:
> - `pii eq 'Yes'` (string)
> - `PII eq 'Yes'`
> - `pii eq true` (boolean)
> - or if `pii` isn’t filterable (then fix index schema or avoid filter and do post-filtering)

---

### Step 1 — Fix AISearchService to support filters and kwargs safely

**File**: `app/core/ai_search_service.py`

Requirements:
- `search_metadata(query: str, top: int=..., filter: str|None=None, select: list[str]|None=None, **kwargs)`
- The underlying `search_impl` must accept `**kwargs` and pass them to Azure Search client.

#### Example pattern (SDK-compatible)
```python
# inside your production implementation:
results = self.search_client.search(
    search_text=search_text,
    filter=filter_expr,
    top=top,
    select=select_fields,
)
```

#### Key fix for the lambda issue
If you keep an injectable `search_impl`, define it like:
```python
self.search_impl = lambda query, top_k=10, **kwargs: list(
    self.search_client.search(search_text=query, top=top_k, **kwargs)
)
```

And update **all tests/mocks** that define `search_impl` to accept `**kwargs`.

---

### Step 2 — Fix the PII/metadata query builder to use structured filters

**File(s)**: one of these exists in your repo; pick the real place:
- `app/core/query_builder.py` OR `app/core/metadata_query_builder.py` OR inside `orchestrator.py`

Rules for PII questions:
- Use `search_text="*"` (or empty string if you prefer) to get broad match.
- Use `filter` to restrict to PII/Confidential rows.

Build filter based on index schema from Step 0:

**If field is string Yes/No**
- `filter = "pii eq 'Yes'"`

**If field is boolean**
- `filter = "pii eq true"`

Also support user-scoped table:
- If user mentions a table/view name, add:
  - `and table_name eq 'v_dlv_dep_prty_clr'` (or whatever field holds it)

Important: **use the exact field name from the index** (case-sensitive).

---

### Step 3 — Orchestrator: never fall back to SQL for metadata/PII intent

**File**: `app/core/orchestrator.py` (or your router layer)

Logic:
- If planner says `intent == METADATA_LOOKUP` (or similar):
  1) Call AI Search
  2) If hits: format results and return
  3) If 0 hits: return clarifying question or “no metadata found”
  4) Stop — do **not** call LLM SQL generation or sqlite execution

Also ensure the event stream shows correct sequence and does not include SQL steps.

---

### Step 4 — Presenter: user-friendly output (no raw SQL, no stack traces)

**File**: `app/core/metadata_presenter.py` (create if missing) or existing formatter

Output format:
- Title: “PII-related fields I found”
- Provide 10–20 items:
  - `table.column — classification (PII: Yes, PCI: No, Security: Confidential)`
- Then ask: “Do you want this for all tables or a specific table/view?”

Do not include:
- raw SQL
- exception traces
- the full QueryResult debug dump (that belongs in debug mode only)

---

### Step 5 — Add backend tests

Create: `tests/test_metadata_pii_search.py`

Test cases:
1) `test_build_pii_filter_string_yes_no()`
   - Assert filter is `"pii eq 'Yes'"` (or whichever your schema indicates)
   - Assert search_text is `"*"` for PII intent

2) `test_orchestrator_metadata_route_no_sql_called(mocker)`
   - Mock `ai_search_service.search_metadata` to return hits
   - Spy on `sql_service.execute_sql` and LLM SQL generation; assert **not called**
   - Assert final answer includes at least one `table.column`

3) `test_orchestrator_metadata_no_hits_returns_clarify()`
   - Mock ai search returns empty
   - Assert assistant asks a clarification question and does not call SQL path

4) `test_ai_search_service_accepts_filter_kwargs()`
   - Create a fake `search_impl` that accepts `**kwargs`
   - Ensure `filter` can be passed without raising

---

### Step 6 — CLI verification commands (must pass)

From repo root:

```bash
pytest -q
```

Then:

```bash
.venv/bin/python -m app.main_cli "show me the columns that have PII information"
```

Expected:
- Events include `[ai_search]`
- No SQL printed/generated
- Assistant returns a list of PII fields (if index seeded) OR asks clarifying question

Also test table-scoped:
```bash
.venv/bin/python -m app.main_cli "show me PII columns for v_dlv_dep_agmt_clr"
```

---

## Troubleshooting checklist (when it still returns 0)

1) Confirm index actually contains PII rows:
- Use `scripts/debug_ai_search_query.py --search "*" --filter "pii eq 'Yes'"`

2) Confirm filter field name:
- Index schema may be `PII`, `pii`, `is_pii`, etc.

3) Confirm field is filterable:
- If not filterable, either:
  - update index schema (recommended), or
  - retrieve broader results and filter in Python (acceptable for small result sets)

4) Confirm value types:
- String `Yes/No` vs boolean `true/false`

---

## Deliverables

- Fixed AI Search service (kwargs + filter supported)
- Correct PII query builder (filter-based)
- Orchestrator stops SQL fallback for metadata intent
- User-friendly presenter for PII results
- New debug scripts for index schema + query
- New tests for routing + filter + kwargs
