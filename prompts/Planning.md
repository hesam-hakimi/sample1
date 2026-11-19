Add `/jira-probe project-check` to the existing jira-probe skill and run
one live, read-only check for the ASKTD project. The existing pat-check
already confirmed authentication against our internal Jira.

Update SKILL.md and scripts/jira_probe.py. Reuse the working pat-check
logic for JIRA_TOKEN, verified TLS, timeout, and redirect refusal.
Preserve the existing commands. Do not open or print .env in chat.

For project-check, make exactly one live request:
GET https://track.td.com/rest/api/2/project/ASKTD

Exit 0 only if Jira returns HTTP 200 with a JSON project object whose
`key` is exactly `ASKTD`. On success, print only:
{"project_visible": true, "project_key": "ASKTD", "http_status": 200}

On failure, exit nonzero and print only project_visible=false, the actual
HTTP status (null if no response arrived), and a short error category.
For HTTP 404, use `not_found_or_not_visible`. Never print the token,
headers, or raw response body.

Test the success and failure paths with mocked responses first. Then run
the project-check script once against internal Jira and show the actual
live output separately from the mock results. Do not rerun pat-check,
query issues, or create or modify anything in Jira. Do not stage or commit.

Finish with the slash command I can use to repeat the check in Copilot.
