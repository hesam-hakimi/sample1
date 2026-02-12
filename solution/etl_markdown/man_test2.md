Bug: Clicking "List Index" triggers:
ManagedIdentityCredential authentication unavailable...
Token request error: (invalid_request) Multiple user assigned identities exist, please specify the clientId/resourceId.

Root cause:
We create ManagedIdentityCredential() without client_id in an environment with multiple user-assigned identities.

Fix requirements:
1) Add config env var:
   AI_SEARCH_MANAGED_IDENTITY_CLIENT_ID (optional)
   Also support AZURE_CLIENT_ID as fallback.

2) Create/Update app/identity.py:
   def get_search_credential(config):
     if config.AI_SEARCH_USE_MSI:
        client_id = config.AI_SEARCH_MANAGED_IDENTITY_CLIENT_ID or os.getenv("AZURE_CLIENT_ID")
        if client_id:
           return ManagedIdentityCredential(client_id=client_id)
        else:
           # still allow system assigned MSI (if only one), but detect ambiguity
           return ManagedIdentityCredential()
     else:
        return AzureCliCredential()

3) Update app/ai_search_service.py (and metadata_store.py):
   - NEVER instantiate ManagedIdentityCredential directly.
   - Always call get_search_credential(config).

4) Improve error handling in list_indexes():
   - Catch azure.core.exceptions.ClientAuthenticationError (and general Exception)
   - If exception message contains "Multiple user assigned identities exist":
       return (False, "Multiple managed identities detected. Set AI_SEARCH_MANAGED_IDENTITY_CLIENT_ID (or AZURE_CLIENT_ID) to the correct client id.")
   - Do not let stack trace crash Gradio event handler.

5) UI (app/ui.py):
   - The "List Index" button handler must:
       ok, indexes_or_msg = ai_search_service.safe_list_indexes()
       if ok: update dropdown choices
       else: show msg in status area (chat or tab)
   - No unhandled exceptions must reach Gradio.

6) Tests:
   - tests/test_identity_client_id.py:
       When config.AI_SEARCH_USE_MSI=true and client id exists -> ManagedIdentityCredential called with client_id
   - tests/test_list_indexes_error_message.py:
       Simulate ClientAuthenticationError with that text -> ensure user-friendly msg returned.

Acceptance criteria:
- Clicking "List Index" never crashes Gradio.
- If client id missing, UI shows actionable message telling user to set AI_SEARCH_MANAGED_IDENTITY_CLIENT_ID/AZURE_CLIENT_ID.
- If client id is set correctly, indexes list loads successfully.
- pytest -q passes.
Return full updated contents for modified/new files.
