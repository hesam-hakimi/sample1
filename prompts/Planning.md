Revise the ASKTD Jira pilot to use this intended hierarchy:

- One Feature named “AskTD” for the entire planning backlog.
- One Epic under that Feature for each Plan, P01 through P15.
- User Stories under their accountable Plan Epic.

Validate one representative chain using read-only Jira requests:
AskTD (Feature) → P01 (Epic) → R1-A (Story).

1. Confirm the exact Jira issue type names in ASKTD. Check the Epic and Story metadata separately. Identify the field on the Epic that can point to the Feature, and the field on the Story that can point to the Epic. The earlier field check was for Task.
2. For each relationship, report the field name, field ID, and what evidence shows it accepts the intended parent type. Distinguish a field available during creation from one that requires a later edit. If the available evidence is insufficient, say exactly what remains unverified. A generic issue link does not establish hierarchy.
3. Check whether the AskTD Feature or either pilot record already exists. If R1-A already exists as a Task, report its key and current parent so we can decide how to reuse it.
4. Show the proposed three records in one table with their type, English summary, and intended parent. Use the canonical planning titles for P01 and R1-A.

Keep this run read-only. Do not create, convert, or reparent any issue. Report in Persian whether this exact three-level structure is supported and what, if anything, still needs confirmation.
