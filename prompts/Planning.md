Inspect the existing Jira Copilot extension source and trace its successful
“Test Connection” action. Identify the exact REST endpoint, authentication
scheme (Bearer PAT, Basic, OAuth, or another method), and how the client
obtains its credentials. Cite the source file and line for each finding.

Check whether the extension already exposes a documented CLI or another
supported interface that a Python script can call. Report what the code
actually implements. Do not read or print stored credential values, make
network requests, or change any files.
