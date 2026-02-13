Fix Gradio error:
WARNING: [UI] Exception in refresh_indexes: 'Button' object has no attribute 'update'

Root cause:
Code is calling <component>.update(...) (e.g., refresh_btn.update(...)).
In our Gradio version, components do not have .update. We must use gr.update(...) and only return updates for components included in outputs.

Tasks:
1) Search the codebase for ".update(" usage on Gradio components (Button/Dropdown/Chatbot/etc).
   Replace any:
     refresh_btn.update(...)
     dropdown.update(...)
     status_box.update(...)
   with returning gr.update(...) from the handler.

2) Refactor refresh_indexes handler so it ONLY returns updates for outputs explicitly wired.
   Example pattern:

   def refresh_indexes():
       try:
           indexes = ai_search_service.list_indexes()  # or safe_list_indexes()
           value = indexes[0] if indexes else None
           return gr.update(choices=indexes, value=value), f"Loaded {len(indexes)} indexes."
       except Exception as e:
           return gr.update(), f"Failed to load indexes: {friendly_message(e)}"

3) Fix event wiring:
   refresh_btn.click(
       fn=refresh_indexes,
       inputs=[],
       outputs=[index_dropdown, status_md],
       queue=True
   )

   IMPORTANT:
   - Do NOT attempt to update the refresh button unless it is included in outputs.
   - If we want to disable the button while running, include it as an output:
       outputs=[refresh_btn, index_dropdown, status_md]
     and return:
       gr.update(interactive=False), gr.update(...), "Refreshing..."
     then re-enable at the end.

4) Add a helper friendly_message(e) that maps common errors (MSI multi-identity, endpoint missing, forbidden) into readable messages.

5) Add tests:
   - test_refresh_indexes_returns_gr_update():
       mock ai_search_service.list_indexes to return ["idx1"]
       assert handler returns (gr.update(...), "Loaded 1...")
   - test_refresh_indexes_error_returns_gr_update():
       mock list_indexes raises Exception("Multiple user assigned identities exist")
       assert status contains instruction to set AI_SEARCH_MANAGED_IDENTITY_CLIENT_ID/AZURE_CLIENT_ID
   (No network calls in tests.)

Acceptance criteria:
- Clicking Refresh Index List no longer throws "'Button' object has no attribute 'update'".
- No stack traces crash Gradio; UI shows status text.
- Outputs returned by handlers match exactly the components in outputs=[...].
Return full modified file contents.
