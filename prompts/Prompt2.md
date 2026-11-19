# Continue the AskTD planning import into Jira

Use the existing jira-probe PAT connection; there is no Jira MCP. Never print the token or write it to a file, log, ledger or Jira field.

## State and authorization

In project ASKTD, Feature ASKTD-1 is the programme container. The 15 Plan Epics are ASKTD-2 (P01) and ASKTD-4 to ASKTD-17 (P02–P15), each with Parent Link ASKTD-1. ASKTD-3 is the pilot Story under P01. Earlier batches of this import created these 17 records.

I authorize, in project ASKTD only: creating up to 52 Stories, one per remaining planning key; updating the 17 existing import records as described below; creating neutral links between imported Stories; and creating one board with its filter.

This remains an import of planning records. It does not start, approve or accept implementation work, and the package stays as it is: `tracker_sync_authorized: false`, `tracker_id: null`.

## Limits

- No application work: no code changes, application tests, dependency installs, flags, secrets or deployments. You may extend the jira-probe skill.
- No git command that changes state (add, commit, stash, reset, clean, checkout, push). The workspace holds paused, uncommitted Task 2 work that must stay exactly as it is.
- The planning package is read-only. Never clear a validation failure by editing the package, the validator or its hashes.
- In Jira: no administration (workflows, schemes, permissions, fields, automation). Never delete, close or transition an issue. Change only the 17 import records and the issues you create; leave any other issue alone and report it.
- New issues are unassigned, stay in the initial backlog status, and get no estimates, dates or sprints.
- Keep the origin of the planning documents out of Jira and out of your reports: no source-system names, URLs or host names. Cite documents by filename, version and section. Jira links are expected in the ledger and the final report.

## 1. Gate

From the folder that contains `feature\`:

```
py -3 -X utf8 -B feature\validation\validate_workflow_traceability.py
py -3 -X utf8 -B -m unittest discover -s feature\validation -p "test_*.py"
```

The validator must exit 0 and report 12 review rows, 53 tasks, 46 outputs, 15 plans, 25 dependencies, 16 checks and 7 architecture decisions. In the test suite, the one alias test that creates a symbolic link cannot run on this machine (WinError 1314): accept that single error and nothing else. If the gate fails, stop and tell me.

Parse JSON with the validator's `unique_object_pairs` hook, and query the register with scripts instead of loading it into the conversation. `TASK_DELIVERY_REGISTER.json` is the source of record for the 53 planning keys, the 46 output keys and DEP01–DEP25. `ASKTD_PLAN_AND_LINEAGE_REFERENCE.md` v0.4, section 6, holds the current Plan definitions. Each document states its version in its header.

## 2. Existing records

Read back ASKTD-1, ASKTD-2 and ASKTD-3 and keep their conventions: summary naming, marker form, description format, and the way a Story is attached to its Epic.

The Plan Epics were written from `AskTD_Delivery_Plans_and_Dependencies.md` v0.2, which keeps older Plan titles and output names: 8 of its 15 titles differ from the v0.4 reference and 17 of the 46 canonical output keys do not appear in it. Prepare an update that brings each Epic in line with section 6 of the v0.4 reference: title (Summary and Epic Name), outcome, named outputs, work, inputs and acceptance. Keep the marker and the Parent Link. Add a "Portfolio dependencies" section that shows each DEP record the Plan consumes with its ID, `required_output`, `consuming_activity`, `kind_and_scope` and `status` as recorded, adding nothing (no producer, no satisfaction, no single kind where the record is mixed or conditional).

Bring ASKTD-3 in line with the Story rules below, and add the label `asktd-planning` to all 17 records.

## 3. Stories

Create one Story per planning key under the Epic of its Plan. Keys stay separate even where they touch the same area (Task 2 and MIG-04; Connections and CONN-01–05); don't merge them or move scope between them. An alias is the same item (FND-01 is Task 3). FND-03 has no Plan: create it without an Epic if the project allows that; otherwise mark it blocked until the Plan is decided. Outputs, DEP records, review rows, DM/DW checks, architecture-decision outlines and open decisions never become issues.

Where the register marks a key as an alias or candidate, state in the Story that reconciliation with existing application work is still pending. Mark keys the register calls outlines or conditional as outlines rather than ready work, with their release or condition.

Render Story text by script from the register rather than retyping it. Records do not all carry the same fields, so render what each one has. Each Story must stand on its own and include:

- planning key, title, scope, exclusions and deliverables;
- Plan and primary outputs (`outputs`), with contributing outputs (`contributes`) listed separately;
- release contribution and any `condition`;
- dependencies, as described below;
- acceptance criteria and required evidence;
- DM/DW checks from the task's own lists (`deposit_migration_checks`, `durable_workflow_checks`), never inferred from its review rows: a row's checks do not apply to every task in that row;
- review rows by key and title, as references only, and open decisions only where the register connects them to this key;
- source document, version and section.

Keep the register's evidence classes apart exactly as recorded (documented requirement, dated implementation report, verified acceptance, unknown) and never upgrade one. Leave out proposed person placeholders.

Write all 155 task dependency records into their consuming Stories with kind (H, C, G or O), input, activity, condition and recorded satisfaction. None is recorded as unmet, so expect zero "blocks" links ("not established" is not unmet). The 65 records that name a producing task form 62 distinct pairs: link each pair once with the neutral "relates to" type.

Every Story gets the label `asktd-planning` and a marker in the form the existing records use, such as `asktd-planning:task:RUN-01`; replace a space in a key with a hyphen (`asktd-planning:task:Task-2`) unless ASKTD-3 already shows another form. Before each create, search for that marker so nothing is created twice.

## 4. Approval

Save the plan as `asktd-jira-import/manifest.json`, outside the package: every intended operation (Epic updates, Stories, links, board and filter) with its disposition (create, update, no change, conflict or blocked), reason and payload. Then show me a short summary: the 15 Epics with current title and v0.4 title; the 53 keys with Plan, Epic and disposition; counts for the 68 planning identities, the links and the board; anything conflicting or blocked; one complete Epic payload and one complete Story payload. Wait for my go-ahead. A created issue cannot be taken back, so this is the one checkpoint; after it, run to the end without asking again.

## 5. Apply

Start with one Epic update and one new Story. Read them back and confirm that type and parent are right, the description renders properly, and a search by label and marker finds them. If the pair fails, stop all further writes and tell me. Otherwise continue one Plan at a time, re-reading each existing record just before you edit it.

Log each write in `asktd-jira-import/ledger.json` before you send it, and add the observed result (Jira key, link, read-back) afterwards. If earlier batches left no ledger, create it and enter ASKTD-1 to ASKTD-17 from read-back; if one exists, continue from it. The ledger also records the versions and hashes of the package files you used. If a create times out or its outcome is unclear, look for the issue by its full marker, and among issues you created in the last few minutes, before trying again. If you still cannot tell, do not retry that create; report it.

## 6. Board

The imported issues must be visible on a board. Use the project's existing board if it already shows them. Otherwise create a Kanban board on the filter `project = ASKTD AND labels = "asktd-planning" ORDER BY Rank ASC` if my permissions allow it; if they don't, give me that JQL and the manual steps. Don't change the configuration of a board other people use.

## 7. Finish

Read back everything you created or changed (type, parent, marker, label, status, assignee, links) and report from that read-back, not from what you intended:

- all 53 planning keys with disposition and Jira link, plus the 15 Plan Epics, the Feature and the board;
- counts of created, updated, unchanged, conflicting, blocked, failed and uncertain operations;
- what Jira could not do, listed as pending rather than done;
- the decisions you still need from me.

Then stop. Don't start implementation or set up recurring synchronization.
