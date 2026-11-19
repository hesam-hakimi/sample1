In the current Windows VS Code workspace, add a new `/jira-probe pat-check`
command to the existing Jira skill. Implement it now. The existing skill
already supports local, public, server-info, and OAuth login. Preserve
those commands.

Update these two files:
- .github/skills/jira-probe/SKILL.md
- .github/skills/jira-probe/scripts/jira_probe.py

The purpose of pat-check is to verify that my Personal Access Token works
with our internal Jira. I will put the token in the workspace-root `.env`
file under the exact key `JIRA_TOKEN`. I will manage that file myself.

1. Use Python 3 and the standard library. At runtime, locate the root
   `.env` relative to the script location and read only `JIRA_TOKEN`.
   Split the assignment on the first `=` so the token value stays intact.
   If the file, key, or value is missing, print a clear error, exit with
   a nonzero code, and make no network request.

2. Make one read-only GET request to:
   https://track.td.com/rest/api/2/myself
   Send `Authorization: Bearer <JIRA_TOKEN>` and `Accept: application/json`.
   Keep TLS verification enabled, set a timeout, and do not follow redirects.

3. Report success only for HTTP 200 with a JSON user object containing a
   non-empty identity field such as `name` or `key`. A 200 HTML sign-in
   page must count as failure. Print only the HTTP status, a boolean
   `authenticated_user_confirmed`, and a short error category on failure.
   Never print the token, headers, response body, or user identity.

4. During implementation, leave my real `.env` untouched and do not open
   it. Test with a temporary `.env`, a dummy token, and mocked responses.
   Cover a valid Jira response, HTTP 401, a 200 HTML sign-in page, and
   a missing token. Verify from Git metadata that the root `.env` is
   ignored and untracked. Flag any issue without staging or committing.

5. Update SKILL.md so `/jira-probe pat-check` invokes the new command.
   Report the tests you actually ran. Leave the live test for me and
   finish by showing this exact Windows command:

   py -3 ".github\skills\jira-probe\scripts\jira_probe.py" pat-check
