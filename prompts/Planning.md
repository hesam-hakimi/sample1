AskTD planning import into Jira

Goal

Put the AskTD / askAlpha delivery plan into the Jira project ASKTD (https://track.td.com/projects/ASKTD) through the Jira MCP: the 15 Plans as containers, the planning keys as issues under them, and a board that shows them. The plan is the planning package already copied into this workspace; start at ASKTD_NEW_SESSION_PROMPT.md.

This is a one-time import of planning records. Creating an issue does not start, approve or accept any implementation work.

The package says tracker synchronization is paused and carries tracker_sync_authorized: false. This message lifts that pause for this Jira import only. Leave the package as it is: its flags stay false, tracker_id stays null, and the mapping to Jira lives in your own ledger.

Limits

	•	No application work: no code changes, application tests, dependency installs, flags, secrets or deployments.
	•	No git command that changes state (add, commit, stash, reset, clean, checkout, push). The workspace holds paused, uncommitted Task 2 work that must stay exactly as it is.
	•	The planning package is read-only. Never clear a validation failure by editing the package, the validator or its hashes.
	•	In Jira: no administration (workflows, schemes, permissions, fields, automation). Never delete, close or transition an issue, and never overwrite text, assignee, status or parent that a person set.
	•	New issues are unassigned, stay in the initial backlog status, and get no estimates, dates or sprints.
	•	Keep the origin of the planning documents out of Jira and out of your reports: no source-system names, URLs or host names. Cite documents by filename, version and section. Links to the target Jira issues and board are expected in the ledger and the final report.

1. Check the package, then read it

From the folder that contains feature/, run the documentation checks (these are not application tests):

python -X utf8 -B feature/validation/validate_workflow_traceability.py
python -X utf8 -B -m unittest discover -s feature/validation -p "test_*.py"

Expect exit code 0, all tests passing, and a validator report of 12 review rows, 53 tasks, 46 outputs, 15 plans, 25 dependencies, 16 checks and 7 architecture decisions. If anything differs, stop and tell me.

Then follow the reading list in ASKTD_NEW_SESSION_PROMPT.md on the local files; its instruction to fetch documents from a remote source does not apply. The register alone is about 450 KB, so query the package with small scripts instead of loading it into the conversation, and parse JSON with the validator's unique_object_pairs hook so duplicate keys are rejected.

TASK_DELIVERY_REGISTER.json is the source of record for the 53 planning keys, the 46 output keys and DEP01–DEP25; ASKTD_PLAN_AND_LINEAGE_REFERENCE.md defines the 15 Plans. Each document states its version in its header.

2. Learn the real Jira project (read-only)

Find out rather than assume: issue types and how they nest, required fields, what I may create, edit and link, the initial status, whether issues can be unassigned, the text format descriptions need, and which Epics, Features, issues and boards already exist.

3. Plan the import, then wait for my approval

What becomes an issue:

	•	Each Plan P01–P15: one container at the level directly above Story/Task in this project (Epic or Feature, not both). If the project has a further level above that, propose how to use it instead of deciding silently.
	•	Each planning key: one Story or Task under its Plan. Keys stay separate even where they touch the same area (Task 2 and MIG-04; Connections and CONN-01–05); don't merge them or move scope between them. An alias is the same item (FND-01 is Task 3). FND-03 has no Plan: create it without a parent if the project allows that; if a parent is mandatory, mark it blocked until the Plan is decided.
	•	Nothing else. Outputs, DEP records, review rows, DM/DW checks, architecture-decision outlines and open decisions are referenced inside issues.

Before creating anything, search Jira (open and closed, every page) for existing equivalents of the Plans and keys, matching on scope rather than title. Adopt an issue only if its scope, type and parent fit your mapping. Record a conflict, and leave the issues alone, when two keys point to one issue, several issues match one key, or adopting would change a parent that a person set. Where a key the register marks as an alias or candidate has no match in Jira, create it and state that reconciliation with existing application work is still pending. Keys the register marks as outlines or conditional also get an issue, clearly marked as an outline rather than ready work, with its release or condition.

Render issue text by script from the register rather than retyping it. Records do not all carry the same fields, so render what each one has. Each issue must stand on its own and include:

	•	planning key, title, scope, exclusions and deliverables;
	•	Plan and primary outputs (outputs), with contributing outputs (contributes) listed separately;
	•	release contribution and any condition;
	•	dependencies, as described below;
	•	acceptance criteria and required evidence;
	•	DM/DW checks from the task's own lists (deposit_migration_checks, durable_workflow_checks), never inferred from its review rows: a row's checks do not apply to every task in that row;
	•	review rows by key and title, as references only, and open decisions only where the register connects them to this key;
	•	source document, version and section.

Keep the register's evidence classes apart exactly as recorded (documented requirement, dated implementation report, verified acceptance, unknown) and never upgrade one. Leave out proposed person placeholders.

Dependencies keep the typed, activity-level meaning the package gives them (H, C, G, O). Write all 155 task dependency records into their consuming issues with kind, input, activity, condition and recorded satisfaction. None is recorded as unmet, so expect zero "blocks" links ("not established" is not unmet). The 65 records that name a producing task form 62 distinct pairs: link each pair once with the neutral "relates to" type unless the link already exists. DEP01–DEP25 have their own fields: show each on the consuming Plans' containers with its ID, required_output, consuming_activity, kind_and_scope and status as recorded, adding nothing (no producer, no satisfaction, no single kind where the record is mixed or conditional).

Every issue you create or adopt gets the shared label asktd-planning and a stable marker in its description, lower-case and without spaces: asktd-planning:plan:p05, asktd-planning:task:run-01, asktd-planning:task:task-2. Markers never change when documents change. On an adopted issue, add only the label and one clearly delimited "AskTD planning" section; if that would conflict with what is already there, record a conflict and leave the issue alone.

Save the plan as asktd-jira-import/manifest.json, outside the package: the hierarchy you found, the mapping you chose, and every intended operation (containers, issues, links, any board or filter) with its disposition (create, adopt, no change, conflict or blocked), reason and payload. Then show me a short summary: hierarchy and mapping; counts per disposition for the 68 planning identities (15 Plans and 53 keys), plus link and board operations; anything conflicting or blocked; one complete Plan payload and one complete child payload. Wait for my go-ahead. Under these limits a created issue cannot be taken back, so this is the one checkpoint; after it, run to the end without asking again.

4. Apply

Start with the first approved Plan and one of its children, whatever their dispositions. Read them back and confirm that type and parent are right, the description renders properly, and a search by label and marker finds them. If the pair fails, stop all further writes and tell me. Otherwise continue, containers first, one Plan at a time, re-reading any existing issue just before you edit it.

Log each write in asktd-jira-import/ledger.json before you send it, and add the observed result (Jira key, link, read-back) afterwards; the ledger also records the versions and hashes of the package files you used. If the ledger already exists when you start, continue from it instead of starting over. If a create times out or its outcome is unclear, look for the issue by its full marker, and among issues you created in the last few minutes, before trying again. If you still cannot tell, do not retry that create; report it.

5. Board

The imported issues must be visible on a board. Use the project's existing board if it already shows them. Otherwise create a Kanban board on the filter project = ASKTD AND labels = "asktd-planning" ORDER BY Rank ASC if the MCP and my permissions allow it; if they don't, give me that JQL and the manual steps. Don't change the configuration of a board other people use.

6. Finish

Read back everything you created or changed (type, parent, marker, status, assignee, links) and report from that read-back, not from what you intended:

	•	all 53 planning keys with disposition and Jira link, plus the 15 Plan containers and the board;
	•	counts of created, adopted, unchanged, conflicting, blocked, failed and uncertain operations;
	•	what Jira or the MCP could not do, listed as pending rather than done;
	•	the decisions you still need from me.

Then stop. Don't start implementation or set up recurring synchronization.
