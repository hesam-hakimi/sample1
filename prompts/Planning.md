Build and test a working VS Code Copilot Agent Skill named `jira-probe` in the current workspace. Create the files yourself and run the tests. I cannot copy or move files manually.

I use Windows. My internal Jira base URL is https://track.td.com. I think we use Jira Server or Data Center, but the deployment type is unconfirmed. VS Code reports that my account policy sets chat.mcp.access to "none". I want to test what a Skill plus a Python script can actually do.

Create these two files:
- .github/skills/jira-probe/SKILL.md
- .github/skills/jira-probe/scripts/jira_probe.py

Keep all changes inside that skill folder. Preserve existing workspace changes. Use Python 3 and its standard library. Do not install packages, change VS Code settings, or commit anything.

Implement three commands:

1. `/jira-probe local`
   Run the bundled Python script in the terminal. Return JSON containing a newly generated run_id and a sample issue key and status. This tests whether Copilot actually executed the script. The skill must return the real terminal output.

2. `/jira-probe public`
   Use the script to read this public Jira issue without credentials:
   https://jira.atlassian.com/rest/api/2/issue/JRASERVER-63150?fields=summary,status
   Return the HTTP status, issue key, summary, status, and run_id. If the request fails, show the actual error. Never substitute the local sample.

3. `/jira-probe server-info`
   For internal Jira, use an existing connection explicitly approved for scripted use by Copilot, if one is available. Through that connection, make one read-only GET request to /rest/api/2/serverInfo. Report the HTTP status and the exact version and deploymentType returned. If deploymentType is missing or ambiguous, say so. If there is no approved connection available, report that as the blocker. Do not extract credentials from the Jira extension, ask me to paste a token into chat, or disable TLS verification.

Put valid name and description frontmatter in SKILL.md. Make `/jira-probe` discoverable in a new Copilot Agent chat. On Windows, use an available Python 3 interpreter, trying `py -3` first.

After creating the files, run the local and public script commands now and show their actual results. Distinguish running the Python script from invoking the Skill through Copilot. Then give me the exact slash command to type in a fresh chat to verify Skill discovery and execution on my machine.
