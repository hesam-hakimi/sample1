# Text2SQL — Fix Streamlit crash: `AttributeError: 'LLMService' object has no attribute 'chat_completion'`

You are working inside the repo that contains the Streamlit Text2SQL app.

## Goal
When running:
```bash
.venv/bin/streamlit run app/ui/streamlit_app.py
```
and the user types **“hi”**, the app must **not crash**. It must complete the **two‑phase LLM router** flow:
1) **Planner** LLM call returns a JSON plan (whether tools are needed).  
2) If no tools → **Responder** LLM call returns the final assistant message.  
   If tools → run tools → **Finalizer** LLM call returns final assistant message (using tool results).

Right now it crashes at:
- `app/core/llm_router.py` → calling `self.llm_service.chat_completion(...)`
- But `LLMService` has **no** `chat_completion` method.

## What to change (high level)
Implement a **single, reusable** `chat_completion()` method on `LLMService` (in `app/core/llm_service.py`) and update callers (if needed) so:
- Planner can request **JSON** outputs safely.
- Responder/Finalizer can request **text** outputs.
- Existing methods like `generate_sql(...)`, `extract_sql(...)`, `interpret_result(...)` keep working and ideally **reuse** the same internal OpenAI/Azure OpenAI client code path.

---

## Step 1 — Locate `LLMService`
Find the class definition:
- `app/core/llm_service.py` (or similar)
Search for:
- `class LLMService:`
- existing methods that already call the LLM (e.g., `generate_sql`, `call_llm`, `_chat`, `complete`, etc.)

**Key requirement:** Do **not** duplicate LLM calling logic. Add `chat_completion()` and have existing methods reuse it (or vice‑versa).

---

## Step 2 — Add `chat_completion()` to `LLMService`
Add this method to `LLMService` (names/fields may be adjusted to match the repo’s config/client):

### Required signature (recommended)
```python
from __future__ import annotations

from typing import Any, Optional

class LLMService:
    ...

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> str:
        """Return assistant message content as a string.

        - `messages` is OpenAI-style: [{"role":"system","content":"..."}, ...]
        - `response_format` supports JSON mode when provided (planner).
        """
        ...
```

### Implementation rules
1) **Reuse existing client/config.**  
   If `LLMService` already has something like `self.client` / `self.azure_client` / `self.cfg`, use that.
2) **Return string content only** (router parses JSON itself).
3) **Support JSON mode** for planner:
   - For OpenAI/Azure OpenAI: pass `response_format={"type": "json_object"}` when the router asks for it.
4) Add minimal, safe error handling:
   - If the response has no choices or no content, raise a clear exception (so trace shows a real problem).

### Example implementation (OpenAI python SDK 1.x style)
**IMPORTANT:** This is a template. You must adapt to how your repo creates the client and stores config.
```python
def chat_completion(
    self,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    model: str | None = None,
) -> str:
    mdl = model or getattr(self.cfg, "llm_model", None) or getattr(self.cfg, "model", None)
    if not mdl:
        raise ValueError("No model configured for LLMService (cfg.llm_model/cfg.model is missing).")

    kwargs: dict[str, Any] = {
        "model": mdl,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if response_format is not None:
        kwargs["response_format"] = response_format

    # Use the same client you already use for generate_sql()
    resp = self.client.chat.completions.create(**kwargs)

    try:
        content = resp.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"LLM response missing content/choices: {e}") from e

    if not content:
        raise RuntimeError("LLM response content is empty.")
    return content
```

If your repo uses **AzureOpenAI**, the call is typically the same shape; only client initialization differs.
Do NOT re-initialize the client if it already exists.

---

## Step 3 — Ensure router uses `chat_completion()` correctly
Open:
- `app/core/llm_router.py`

You should see something like:
```python
plan_json = self.llm_service.chat_completion(...)
```
Make sure the **planner** call passes JSON mode:
```python
plan_json = self.llm_service.chat_completion(
    messages,
    temperature=0.0,
    response_format={"type": "json_object"},
)
```
And responder/finalizer calls do **not** require JSON mode (unless you intentionally want structured output).

**Do not rename router methods.** Fix must be minimal and forward-compatible.

---

## Step 4 — Add a small unit test (no network calls)
We want to prevent this exact regression (missing method) in the future.

Create or update a test such as:
- `app/ui/test_llm_service_contract.py` or `tests/test_llm_service_contract.py`

### Test requirements
- Must not call the network.
- Just confirms the method exists and can be called when client is stubbed.

Example:
```python
def test_llm_service_has_chat_completion():
    from app.core.llm_service import LLMService

    svc = LLMService.__new__(LLMService)  # bypass __init__ if it needs secrets
    assert hasattr(svc, "chat_completion"), "LLMService must expose chat_completion()"
```

Better (if you can inject client/config):
- instantiate normally with a dummy config
- monkeypatch `svc.client.chat.completions.create` to return a fake response

---

## Step 5 — Verify end-to-end
Run:
```bash
.venv/bin/pytest -q
.venv/bin/streamlit run app/ui/streamlit_app.py
```
Then type: **hi**

Expected:
- Activity log shows planner step(s).
- No crash.
- If planner decides no tools: responder returns a friendly greeting.
- If planner decides tools: it calls tools, then finalizer returns merged answer.

---

## Acceptance criteria (must all pass)
- ✅ `pytest -q` passes.
- ✅ Streamlit app starts without crashing.
- ✅ Typing “hi” does **not** trigger tool execution for SQL/AI Search (planner should decide `decision="respond"`).
- ✅ Planner uses JSON response format; router parses it safely.
- ✅ No duplicate LLM call logic added (single source of truth is `LLMService.chat_completion`).

---

## Notes (do not skip)
- Keep `from __future__ import annotations` at the **very top** of any file that uses it (no blank code before it).
- If there are multiple `LLMService` definitions or a legacy file, consolidate to one and update imports, but keep changes minimal.
- If config keys differ (e.g., `cfg.openai_model`, `cfg.azure_openai_deployment`), adapt the method accordingly and keep the router code stable.
