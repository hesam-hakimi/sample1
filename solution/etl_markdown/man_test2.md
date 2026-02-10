# KMAI POC Tracker — README

## Goal
Build a POC where a business user asks a question and the solution:
1) interprets the request,
2) generates SQL,
3) executes it on a database (or equivalent data source),
4) summarizes results back to the user.

## Guiding principles (from meeting)
- Move fast: build a working skeleton now; improve model + access in parallel.
- Track “Strategic” vs “Tactical” (shortcuts) explicitly.
- Two parallel workstreams:
  - Connectivity / data access
  - POC skeleton + prompt/RAG/Text-to-SQL flow
- Daily morning check-in: update status, blockers, next steps.

## Status colors
- 🟢 Green: unblocked / in progress
- 🟡 Yellow: some risk / dependency
- 🔴 Red: blocked (needs decision/escalation)

## Owners
List key people + roles (edit as needed):
- Praveen: overall POC flow & demo readiness
- Savita: program/coordination, escalation (Lalit)
- Ankur: architecture/solution + tracker owner
- Sabita/Samita/Chuck: connectivity exploration
- Hesam: first draft of steps (tracker seed)
- Neha: scheduling / coordination
