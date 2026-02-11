We have a Gradio NL→SQL app. When the user sends a message like "hi", the UI shows:
Error: 'NoneType' object has no attribute 'upper'

Goal:
Fix this bug robustly so greetings or non-SQL questions do NOT crash the app.

Context:
- The pipeline returns a dict like {"sql": "...", "explanation": "...", ...} OR it may return None / missing fields in some cases.
- The UI code likely calls something like: proposed_sql.upper() or sql.upper() without checking for None.
- We must NOT use OpenAI Runner/Agent. Keep current architecture.

Tasks:
1) Locate the exact line causing 'NoneType' has no attribute 'upper' (search for `.upper()` usages in app/ui.py, app/nl2sql.py, app/sql_safety.py).
2) Fix the root cause by enforcing a consistent return type from the NL→SQL pipeline:
   - nl2sql.generate_sql(question) must ALWAYS return a dict with keys:
     - "sql" (string, can be empty string if not applicable)
     - "explanation" (string)
     - "assumptions" (list[str])
     - "needs_confirmation" (list[str])
     - "kind" (one of: "greeting", "clarification", "sql_proposal", "error")
   - Never return None.
3) Add greeting/smalltalk handling:
   - If the user input is short greeting (hi/hello/hey/thanks) OR unrelated to data, return kind="greeting" and sql="" with a friendly message asking what banking question they want answered.
4) Harden SQL safety validators:
   - validate_* functions should raise ValueError if sql is empty/None
   - Any caller must catch ValueError and show it in the chat instead of crashing.
5) Update app/ui.py handlers:
   - If sql == "" then do not render SQL panel as .upper() or process it; just show explanation in chat and keep proposed SQL empty.
   - Make sure gr.State always stores a string for last_sql (default "").
   - Ensure run button refuses to run when last_sql is empty and shows a message.
6) Add tests:
   - tests/test_ui_logic.py: calling send handler with "hi" should not throw, and should return ("greeting", sql="")
   - tests/test_nl2sql.py: generate_sql("hi") returns kind="greeting" and sql=""
   - tests/test_sql_safety.py: validate_business_sql("") raises ValueError
   - Add a regression test to ensure no code path calls `.upper()` on None.

Acceptance criteria:
- Typing "hi" in the Gradio UI shows a friendly response and no exception.
- No `.upper()` call is applied to None anywhere.
- `pytest -q` passes.
- Provide the full updated content for any modified files.
