Bug:
When clicking "Refresh Index List" in Gradio, the page becomes stuck and DevTools shows:
Failed to load resource: net::ERR_INCOMPLETE_CHUNKED_ENCODING
.../gradio_api/heartbeat/...

Meaning:
Backend request crashed or never returned (blocked). We need robust refresh handler:
- No unhandled exceptions
- No infinite event recursion
- Timeouts for Azure calls
- Disable button while running
- Always return valid Gradio updates

Implement:

1) Add a safe wrapper utility (new file app/safe_call.py):
   - def run_with_timeout(fn, timeout_s) -> (ok, value_or_error_msg)
   - Use concurrent.futures.ThreadPoolExecutor with future.result(timeout=timeout_s)
   - Catch Exception and return friendly error (string), do NOT raise.

2) In app/ai_search_service.py:
   - Add method safe_list_indexes(timeout_s=10) -> tuple[bool, list[str] | str]
     Internally calls list_indexes() via run_with_timeout.
   - list_indexes() must be pure and not print; raise exceptions normally.
   - In safe_list_indexes, map exceptions to friendly messages:
       - "Multiple user assigned identities exist" -> instruct set AI_SEARCH_MANAGED_IDENTITY_CLIENT_ID or AZURE_CLIENT_ID
       - endpoint missing -> instruct set AI_SEARCH_ENDPOINT
       - forbidden/unauthorized -> instruct RBAC roles for Search Index Data Reader/Contributor
     Never leak stack traces to UI.

3) Fix event wiring in app/ui.py to prevent loops:
   - The Refresh button click is the ONLY thing that calls refresh_indexes().
   - Dropdown .change should ONLY set selected_index state, and must NOT call refresh.
   - Do not use any "every=" timers for refresh.
   - Ensure refresh handler DOES NOT trigger itself:
       refresh handler returns dropdown update + status update only.

4) Implement refresh handler with re-entrancy guard:
   - Use gr.State refresh_in_progress (bool) OR a threading.Lock in module scope.
   - If refresh already running, immediately return:
       - keep dropdown unchanged
       - status: "Refresh already in progress…"
   - While running, disable the Refresh button (interactive=False) and re-enable at end.

5) Ensure correct return types:
   - For dropdown update use gr.update(choices=indexes, value=value_if_present)
   - For status use a textbox/markdown.
   - Never return None where Gradio expects updates.
   - Chatbot remains list[{"role","content"}] only.

6) Add logging (server-side) so we can see why it freezes:
   - log start/end + elapsed time for refresh handler
   - log exception messages (not trace) at warning level

7) Tests (no Azure network):
   - tests/test_refresh_timeout.py:
       mock ai_search_service.list_indexes to sleep longer than timeout
       assert safe_list_indexes returns ok=False and a friendly timeout message
   - tests/test_refresh_identity_error.py:
       mock list_indexes raising Exception("Multiple user assigned identities exist")
       assert returned message mentions setting client id
   - tests/test_ui_no_recursion.py:
       unit-test that dropdown change handler does not call refresh function (mock and assert not called)

Acceptance criteria:
- Clicking Refresh Index List never freezes the UI.
- If Azure call blocks, UI shows a timeout message within 10s.
- Heartbeat error disappears (backend no longer crashes/hangs).
- No infinite refresh recursion.
- pytest -q passes.
Return full updated contents for modified/new files.

