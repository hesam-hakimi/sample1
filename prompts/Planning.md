Extend the existing jira-probe skill with `/jira-probe login` for
browser-based OAuth 2.0. Make the changes directly in the workspace.
Keep the existing local and public probes working.

Implement a one-shot, read-only login test for Jira Server/Data Center:
open the system browser, use Authorization Code with PKCE (S256), validate
the callback state, then call GET /rest/api/2/myself using the access
token. Keep tokens in memory for this test. Report only the HTTP status
and whether Jira confirmed the authenticated user.

Use the OAuth registration intended for this integration, including its
exact redirect URI and READ scope. Account for the client authentication
required by the installed Jira version. Never embed a shared client
secret in the skill or print tokens, authorization codes, or callback
query strings. Do not fall back to PAT.

If registration details are missing, still implement and test the flow
locally with a simulated provider. Test successful login, denied consent,
and a mismatched state. Then tell me exactly which registration details
are needed for a live run and where to configure them. Clearly distinguish
the local test results from a successful login to our internal Jira.
