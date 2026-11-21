# Make the imported Stories readable and easy to find

The Stories imported into ASKTD are accurate but hard to use: they open with planning metadata, use codes nobody explains, point to documents a Jira reader cannot open, and carry a single label. Add a short plain-language brief to the top of each Story, so that a developer or coding agent who has never seen the planning package understands what the Story asks for, why, and what has to happen first. Add labels so the records can be filtered.

Use the existing jira-probe PAT connection. The limits of the import still apply: these are planning records, nothing is started or approved, the package is read-only, and no issue is transitioned, assigned, estimated, dated or put in a sprint.

## Where things stand

An earlier session prepared pilot briefs and was stopped by a host permission denial before the approval checkpoint. No Jira description has been changed. Treat the files in `asktd-jira-import/briefs/` as superseded and leave them untouched; write everything for this run as new files in `asktd-jira-import/briefs-v2/`. If the host refuses a file or terminal action, stop and tell me which action it was instead of trying another route.

## The brief

Write it from the planning package only: the Story's register record, its card, and the document sections that record cites. Add no scope, requirement, date or decision that those sources do not state. Where they are silent, write "not defined yet" instead of filling the gap, and keep reported or unverified things labelled as such.

Spell the meaning out instead of pointing to a document: a reader should not need a file to understand a sentence. A brief is a summary, and the planning record below it keeps the detail: about 150 words for an outline, about 250 for an ordinary Story, 400 at most for the most complex one. Sections, in this order:

- **In short**: two or three sentences on what will exist when this is done.
- **Why**: the problem it solves.
- **What to deliver**: the deliverables as short plain steps.
- **Done when**: the acceptance criteria in plain words, naming each DM/DW check by what it proves.
- **First step**: from the record's `next` field.
- **Needs from others**: one line per dependency, saying what is needed, from which Plan or Story, and whether it is a hard input, something to agree, a gate, or conditional.
- **Not in scope**: the exclusions.
- **Ready?**: the honest status.
- **Terms**: one line for each project term a newcomer would not know.

Keep the marker as the first line. Put the brief directly below it and end it with "If this brief and the planning record differ, the record wins." Then keep the existing text under the heading "Planning record (source of truth)". In that record, drop lines that only say "None recorded", write each dependency on one line, and add the record's `next`, `owner_role` and `reviewers` fields (roles only, no person placeholders).

On the Feature ASKTD-1, add one short "How to read these Stories" section: what H, C, G and O mean, what the evidence classes mean, and what "outline" and "planning candidate" mean.

## Labels and search

Derive labels mechanically from the register; infer nothing. Write them in lower case with the prefix `asktd-`, because labels are shared across the whole Jira site.

- Plan: `asktd-p01` to `asktd-p15` from `plan`, on each Story and on its Plan Epic. FND-03 gets `asktd-plan-open`.
- Release: the first of R1 to R4 named in `release` gives `asktd-r1` to `asktd-r4`; if none is named, `asktd-release-open`. The label is an index, not a commitment; the full release text stays in the description.
- Component: a label made from the component's name in `AskTD_Component_and_Resource_Allocation.md`, for example `asktd-ai-analytics` for CMP-03.
- `asktd-outline` where `key_status` marks an outline key, and `asktd-conditional` where the record has a `condition`.
- `asktd-dm-checks` and `asktd-dw-checks` where the record lists those checks.

Expect 34 Stories on R1, 8 on R2, 4 on R3, 4 on R4 and 3 open; 16 outlines, 6 conditional, 5 with DM checks and 8 with DW checks.

On ASKTD-1, add "How to find things": a handful of JQL queries (one Plan with its Stories, R1 work that is not an outline, Stories with DM or DW checks, a planning key by its summary), each tested to return the expected count. Save the same queries as filters if my permissions allow.

## Pilot first

Start with three Stories: ASKTD-32 (RUN-01), ASKTD-25 (R1-E) and ASKTD-67 (EXPAND-01, an outline). For every sentence of a brief, record which register field or document section supports it. Show me the three briefs in full and the label plan (every label with its count), and wait for my go-ahead before writing anything to Jira.

After I approve the pilot, apply the labels to all records and do the remaining Stories one Plan at a time in the same way, without asking again: record the support, write, read back, and log each write in the ledger. Stop and tell me when a brief cannot be written without guessing.

## Example of the form (RUN-01)

Use this for tone, length and structure; write every other brief from its own sources.

**In short.** Run one existing deposit analysis from an exact published, versioned Recipe through a small shared executor, instead of through the Python function written only for that analysis. Prove on the frozen demo data that the Recipe path gives the right answers before any old code is retired.

**Why.** In the reported pilot the SQL is fixed in code, so changing a Recipe does not change what runs (dated report, not re-verified).

**What to deliver.**
1. A consumer that loads one exact published revision (Metric, Recipe, dependencies, manifest), never "the latest".
2. Explicit enrollment: a published Recipe runs only after it is registered and mapped to a qualified builder/adapter, and it can be disabled or retired.
3. One reviewed declarative Recipe with a minimal executor/adapter contract for one deposit analysis. A Recipe that only calls the old function does not count.
4. A comparison of the old function, the Recipe path and an independent reference, with every difference logged.
5. After acceptance only: the list of code to retire and the cutover/rollback decision.

**Done when.**
- A published draft does not run by itself; unknown, retired or unqualified selections stop safely.
- Every result names the exact revision and source pair it used.
- The Recipe path passes with the old function made unavailable, and no fallback hides a failure.
- Checks DM-01 to DM-08 pass: reproducible baseline, genuine Recipe execution, analytical correctness, response fidelity, stopped requests, discrepancy decisions, cost and latency, controlled retirement.

None of this is verified yet.

**First step.** Inventory the demo and the selected deposit function with its callers; finalize the Recipe/executor contract and the reference matrix.

**Needs from others.**
- Hard input: the selected publication contract from Plan P04 (not all of Task 1).
- To agree with Task 1 (ASKTD-27): the published-artifact handoff.
- Hard input: a qualified builder/binding and current P02 access.
- Hard input: the frozen demo data and independently reviewed expected results (demo reported, not verified).
- Gate before activation: the policy for retired versions and for the provider.

**Not in scope.** Catalogue search, a generic plugin loader, automatic enrollment of everything, replacing all deposit functions, agentic Recipe generation, expanding Task 2, unreviewed schema changes.

**Ready?** No. This is a planning record; reconciliation with the current application is still pending.

**Terms.** Recipe: the approved method for answering an analytical question. Enrollment: the explicit step that lets a published Recipe run. Frozen demo: the demo data held at one fixed revision.

If this brief and the planning record differ, the record wins.
