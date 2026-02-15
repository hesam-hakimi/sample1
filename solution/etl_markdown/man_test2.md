# Copilot Prompt — Fix `response_format` Type Error (OpenAI 400) in Text2SQL Two‑Phase Router

## Context / Error
Running:
```bash
.venv/bin/streamlit run app/ui/streamlit_app.py
```

Crashes when the user says “hi” with:

```
openai.BadRequestError: Error code: 400 - {'error': {'message': "Invalid type for 'response_format': expected an object, but got a string instead.", ...}}
```

Stack (key part):
- `app/core/llm_router.py` calls `self.llm_service.chat_completion(...)`
- `app/core/llm_service.py` (inside `chat_completion`) passes `response_format` to:
  `self.client.chat.completions.create(**kwargs)`
- The OpenAI Python SDK expects `response_format` to be an **object/dict**, not a string.

## Goal
Make the app compatible with the OpenAI Python SDK by ensuring `response_format` is always passed as a **dict** (object), and keep the two‑phase router behavior:
1) **Planner** call returns a JSON plan (tool decision)
2) If tools needed → run tools → **Answer** call returns final response (optionally JSON)

## Requirements (must follow)
- Do **not** remove the two‑phase router behavior.
- Keep existing public APIs as stable as possible.
- Add/adjust tests to prevent regressions.
- Make the fix robust: handle both `response_format` **string** (legacy) and **dict** (new).

---

## Step 1 — Find and update all `response_format` usages
Search the codebase for `response_format=` and identify any places passing a **string** like:
- `"json_object"`
- `"json_schema"`
- `"text"`

Update those callers to pass a dict:
- `{"type": "json_object"}`
- `{"type": "json_schema", "json_schema": {...}}`
- `{"type": "text"}` (if applicable)

You should still implement normalization in `LLMService` (Step 2) so callers can’t break it again.

---

## Step 2 — Patch `app/core/llm_service.py` to normalize `response_format`
### 2.1 Update signature
In `LLMService.chat_completion(...)`, add an explicit parameter for `response_format` that can be:
- `None`
- `dict`
- `str` (legacy support)

Example typing (Python 3.11+):
```python
from typing import Any

def chat_completion(..., response_format: dict[str, Any] | str | None = None, **kwargs) -> str:
    ...
```

### 2.2 Normalize before calling the SDK
Implement a small helper (private function or inline logic) to ensure the SDK always receives an object:
- If `response_format` is `str`, convert to `{"type": <that string>}`
- If it is `dict`, ensure it contains `"type"`
- If it is something else, raise `TypeError` with a clear message

Recommended normalization logic:
```python
def _normalize_response_format(response_format):
    if response_format is None:
        return None
    if isinstance(response_format, str):
        return {"type": response_format}
    if isinstance(response_format, dict):
        if "type" not in response_format:
            raise ValueError("response_format dict must include a 'type' key")
        return response_format
    raise TypeError("response_format must be None, a str, or a dict")
```

Then, when building kwargs for `self.client.chat.completions.create(...)`:
- Only include `response_format` if not None
- Always include it as a dict

### 2.3 Make the error self-explanatory
If the SDK raises an error, wrap/log (where you already log) with:
- model name
- normalized response_format value
- which phase (planner vs answer) if that info is available

---

## Step 3 — Fix the planner call in `app/core/llm_router.py`
Your planner step must produce a machine-readable plan.

### Preferred approach
Use `response_format={"type": "json_object"}` for the planner call, and ensure the prompt instructs the model to output **only JSON**.

Planner constraints:
- No markdown
- No extra text
- Output must parse to JSON

If you already have JSON schema support, you may upgrade to:
`{"type": "json_schema", "json_schema": {...}}`
…but only if the schema is implemented and stable.

**Important:** If you do NOT have schema already, keep it simple with `json_object` for now.

---

## Step 4 — Add tests (must pass)
Add/modify unit tests to ensure:
1) `LLMService.chat_completion` converts string → dict
2) Callers use dict (where easy to test)
3) No regression for normal text calls

### Suggested test strategy
Mock the OpenAI client used inside `LLMService` so no real network calls happen.

Example test cases (pseudo):
- `response_format="json_object"` → SDK called with `{"type": "json_object"}`
- `response_format={"type": "json_object"}` → unchanged
- `response_format={"json_schema": {...}}` (missing type) → raises `ValueError`

If you already have tests folder structure, add a new test file like:
- `app/core/tests/test_llm_service_response_format.py`
(or align with your existing layout)

---

## Step 5 — Verification steps (must include in PR output)
After code changes, run:
```bash
.venv/bin/pytest -q
.venv/bin/streamlit run app/ui/streamlit_app.py
```

Manual check:
- Open app
- Send “hi”
- App should not crash
- Planner trace log should show it called planner successfully
- Assistant should return a short friendly response (or ask a clarification) WITHOUT running SQL/tools unless needed

---

## Acceptance Criteria
- ✅ No `Invalid type for 'response_format'` errors
- ✅ Streamlit app loads and responds to “hi”
- ✅ Planner still returns a JSON plan, tools only run when needed
- ✅ Tests cover string/dict response_format normalization
- ✅ No breaking changes to the overall router design

---

## Notes (do not skip)
- This issue is caused by passing `response_format` as a string into the OpenAI Python SDK.
- The SDK requires `response_format` to be an object/dict, e.g. `{"type": "json_object"}`.
- Fix both the **LLMService** (defensive normalization) and **call sites** (proper dict usage).
