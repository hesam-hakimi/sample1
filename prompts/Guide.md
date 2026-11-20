# Make the imported Stories readable on their own

The Stories imported into ASKTD are accurate but hard to read: they open with planning metadata, use codes nobody explains, and point to documents a Jira reader cannot open. Add a plain-language brief to the top of each Story, so that a developer or coding agent who has never seen the planning package understands what the Story asks for, why, and what has to happen first.

Use the existing jira-probe PAT connection. The limits of the import still apply: these are planning records, nothing is started or approved, the package is read-only, and no issue is transitioned, assigned, estimated, dated or put in a sprint.

## The brief

Write it from the planning package only: the Story's register record, its card, and the document sections that record cites. Add no scope, requirement, date or decision that those sources do not state. Where they are silent, write "not defined yet" instead of filling the gap, and keep reported or unverified things labelled as such.

Spell the meaning out instead of pointing to a document: a reader should not need a file to understand a sentence. Keep it as short as the Story allows: roughly 200 words for a simple Story, up to about 550 for a complex one like the example. Sections, in this order:

- **In short**: two or three sentences on what will exist when this is done.
- **Why**: the problem it solves.
- **What to deliver**: the deliverables as short plain steps.
- **Done when**: the acceptance criteria in plain words, naming each DM/DW check by what it proves.
- **First step**: from the record's `next` field.
- **Needs from others**: one line per dependency, saying what is needed, from which Plan or Story, for which activity, and whether it is a hard input, something to agree, a gate, or conditional.
- **Not in scope**: the exclusions.
- **Ready?**: the honest status.
- **Terms**: one line for every code, abbreviation or project term used above.

Keep the marker as the first line. Put the brief directly below it and end it with "If this brief and the planning record differ, the record wins." Then keep the existing text under the heading "Planning record (source of truth)". In that record, drop lines that only say "None recorded", write each dependency on one line, and add the record's `next`, `owner_role` and `reviewers` fields (roles only, no person placeholders).

On the Feature ASKTD-1, add one short "How to read these Stories" section: what H, C, G and O mean, what the evidence classes mean, and what "outline" and "planning candidate" mean.

## Pilot first

Start with three Stories: ASKTD-32 (RUN-01), one small R1 Story of your choice, and ASKTD-67 (EXPAND-01, an outline). Save the proposed text in `asktd-jira-import/briefs/`, and for every sentence of a brief record which register field or document section supports it. Show me the three briefs in full and wait for my go-ahead before writing anything to Jira. Also tell me whether Priority = High on the Stories is the project default or was set by the import.

After I approve the pilot, do the remaining Stories one Plan at a time in the same way, without asking again: record the support, write, read back, and log each write in the ledger. Stop and tell me when a brief cannot be written without guessing.

## Example of the form (RUN-01)

Use this for tone, length and structure; write every other brief from its own sources.

**In short.** Make the application run one existing deposit analysis from an exact published, versioned Recipe through a small shared executor, instead of through the Python function written only for that analysis. Prove on the frozen demo data that the Recipe path gives the right answers before any old code is retired.

**Why.** In the reported pilot the SQL is fixed in code, so changing a Recipe does not change what runs (dated report, not re-verified). This Story makes one analysis genuinely driven by its Recipe.

**What to deliver.**
1. A consumer that loads one exact published revision of the Metric, Recipe, dependencies and manifest, never "the latest".
2. Explicit enrollment: a published Recipe runs only after it is registered and mapped to a qualified builder/adapter. It can be disabled or retired, and results keep their provenance.
3. One reviewed declarative Recipe and a minimal shared executor/provider-adapter contract for one deposit analysis on the frozen demo data. A Recipe that only calls the old function does not count.
4. A comparison of the old function, the Recipe path and an independently calculated reference, first with structured inputs and then end to end, with every difference logged. MIG-04 and MIG-08 contribute to this.
5. After acceptance only: the list of code that can be retired and the cutover/rollback decision.

**Done when.**
- Publishing a draft does not run it; unknown, retired, unqualified or incompatible selections stop safely.
- Every execution and result names the exact revision and source pair it used.
- The Recipe path still passes with the old function made unavailable; a permitted change to the Recipe changes what runs, and an unsupported one is rejected.
- Checks DM-01 to DM-08 pass: reproducible baseline, genuine Recipe execution, analytical correctness, routing and response fidelity, scope and stopped requests, honest discrepancy decisions, measured cost and latency, controlled retirement.
- Tests on fixtures and real published enrollment stay separate; a fixture is never treated as published.
- No automatic fallback to the old function or to generated SQL hides a failure.

None of this has been verified yet. Success on the demo does not close the real-data, other-provider, LangSmith or complex-graph gates.

**First step.** Inventory the existing demo and the selected deposit function and its callers; finalize the versioned Recipe/executor contract and the independent reference matrix.

**Needs from others.**
- Hard input, for runtime enrollment: the selected publication contract from Plan P04 with its evidence (not the completion of all Task 1).
- To agree with Task 1 (ASKTD-27), for consumer design: the exact published-artifact handoff.
- Hard input, for execution acceptance: a qualified builder/binding and current P02 access.
- Hard input, for the isolated evaluation: the frozen demo/schema and independently reviewed expected results. The owner reports that the demo exists; its contents are not verified.
- Gate before activation: the policy for retired versions and for the provider.

**Not in scope.** Whole-catalogue search, a generic plugin loader, automatic enrollment of every published record, replacing all deposit functions, a universal compiler, agentic Recipe generation, expanding Task 2, unreviewed schema changes.

**Ready?** No. This is a planning record: implementation is paused and reconciliation with the current application is still pending.

**Terms.** Recipe: the approved method for answering an analytical question, including calculations and permitted data dependencies. Enrollment: the explicit step that lets a published Recipe run. Frozen demo: the existing demo data held at one fixed revision. REG-15: the rule that publication alone never enrolls or activates execution. P05: the Plan "Validated answers through both execution routes".

If this brief and the planning record differ, the record wins.
