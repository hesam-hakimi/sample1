We have a Gradio UI with an "Azure AI Search" tab. Clicking the "List Indexes" / "Refresh Index List" button makes the page appear to loop (spinner / repeated requests), and it does not complete.

Goal: Fix the infinite loop / repeated execution. Ensure the button triggers exactly ONE backend call per click. No dropdown-change recursion. No crashes that drop the event stream.

Step 1 — Instrumentation (do this first):
- In the handler function used by the button (e.g., refresh_indexes / list_indexes), add logging:
  - log at function entry with timestamp and incrementing counter (global or stored in gr.State)
  - log before returning (success path)
  - log full exception with stack trace (error path)
- Run with GRADIO_DEBUG=1 and confirm whether the handler is called repeatedly from one click.

Step 2 — Find and remove recursion triggers:
- Search in ui.py (or build_ui) for any of these anti-patterns:
  A) Dropdown.change(fn=refresh_indexes or list_indexes, ...)  -> remove it
  B) refresh_btn.click(...) outputs include a component that then triggers the same click/change handler -> break the cycle
  C) gr.Dropdown(choices=list_indexes())  -> do NOT call list_indexes at UI-build time
  D) Any component uses "live=True" or "every=..." that calls list_indexes -> disable

Step 3 — Correct event wiring:
- "List Indexes" button should be the ONLY trigger to fetch indexes.
- Wire:
  list_btn.click(fn=refresh_indexes, inputs=[], outputs=[index_dropdown, status_md], queue=True or queue=False)
- Ensure refresh_indexes returns updates ONLY for outputs listed above.

Step 4 — Prevent dropdown .change loops:
- If dropdown has a change handler, it must NOT call refresh_indexes.
- If we need to persist selection, use:
  index_dropdown.change(fn=set_selected_index, inputs=[index_dropdown], outputs=[selected_index_state, status_md])
- set_selected_index must not modify index_dropdown itself.

Step 5 — Preserve dropdown value safely (avoid re-trigger):
- In refresh_indexes:
  - fetch new_choices = [...]
  - keep current_value if still in new_choices
  - only set value if current_value is None or not in choices
  - return gr.update(choices=new_choices, value=safe_value)
  - return a human-friendly status message
- IMPORTANT: do not always force value=new_choices[0] on every refresh if a valid value already exists.

Step 6 — Add a concurrency guard (prevents double-click storms):
- Add a gr.State boolean like is_refreshing_state
- At handler start:
  - if is_refreshing_state is True: return gr.update(), "Refresh already running"
  - set it True
- At end (finally): set it False
(If you want to disable the button while running, include the button as an output and return gr.update(interactive=False/True).)

Step 7 — Make the handler crash-proof:
- Wrap in try/except; NEVER raise to Gradio.
- Return stable outputs on error:
  - dropdown update should be gr.update() (no change)
  - status should be friendly, e.g. "Unable to list indexes. Check endpoint, credential, or permissions."
- Specifically handle:
  - ManagedIdentityCredential / multiple identities -> tell user to set AZURE_CLIENT_ID (or managed_identity_client_id)
  - endpoint missing -> tell user to set AI_SEARCH_ENDPOINT

Step 8 — Tests (no network):
- Unit test refresh_indexes using mocks:
  - mock search_client.list_index_names() returning ["a","b"]
  - verify refresh_indexes returns a gr.update with those choices and correct safe value behavior
- Unit test loop prevention:
  - call refresh_indexes twice with is_refreshing_state True in between and ensure second call returns "already running"

Acceptance criteria:
- One click on "List Indexes" results in exactly one backend call (verify by logs).
- Dropdown updates once; no repeated calls triggered by dropdown.change.
- No ERR_INCOMPLETE_CHUNKED_ENCODING in browser; no uncaught exceptions in terminal.
Return the full updated ui.py (and any helper module changes) with clean wiring.
