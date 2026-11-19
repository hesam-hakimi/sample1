Add `/jira-probe permission-check` to the existing skill. Reuse the
working PAT and HTTPS request logic from project-check.

Run one read-only GET request to:
https://track.td.com/rest/api/2/mypermissions?projectKey=ASKTD

Read only `permissions.CREATE_ISSUES.havePermission` from the response.
Report the HTTP status, project key, and `can_create_issues` as true
or false. If the request fails or the field is missing, report it as
unknown. HTTP 200 alone does not establish permission.

Do not print the token or raw response, and do not create or modify
anything in Jira. Show the actual live result.
