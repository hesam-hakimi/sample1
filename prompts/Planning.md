Continue the AskTD Jira import using the existing jira-probe PAT connection. I authorize creating up to 14 Epics in project ASKTD, one for each remaining Plan P02 through P15. The existing programme Feature is ASKTD-1. P01 already exists as ASKTD-2, and its first Story is ASKTD-3.

1. Read back ASKTD-1 and ASKTD-2. Verify their project, types, planning markers, and that ASKTD-2 has Parent Link = ASKTD-1. Use P01 as the working example.

2. Read P02–P15 from the canonical planning package. Before writing, show a compact table with each Plan key, exact source title, and proposed action. Use the P01 naming convention for Summary and Epic Name. Write each English description from that Plan's actual objective, scope, documented outputs, and acceptance criteria where available. Include its source path and stable marker `asktd-planning:plan:<PlanKey>`.

3. Check existing ASKTD issues, including closed issues, before each create. Reuse an Epic when its planning identity, scope, and parent match. If a likely match has a different parent or conflicting identity, report that Plan as a conflict and continue with independent Plans.

4. Create each missing Epic unassigned, with Parent Link (`customfield_19601`) set to ASKTD-1. Read each Epic back and verify its type, marker, and stored parent. Record its Jira key immediately. If a write times out, reconcile by marker before retrying. If Jira rejects or loses the parent relationship, stop further creates and report the last verified Plan.

5. Finish with a P01–P15 table showing each Plan's title, clickable Jira key, outcome, and parent actually read back. Give the verified total and list any gaps.

This batch covers Epics only. Preserve the existing Feature, pilot Story, planning package, and Git worktree
