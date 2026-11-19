Use the existing jira-probe PAT connection for one live pilot in project ASKTD. I authorize creating up to three real planning records, in this order:

1. Feature: AskTD
2. Epic: P01 – Deposits pilot scope and reference answers
3. Story: R1-A – Agree pilot scope and independent reference answers

Use the canonical planning package for the English descriptions and acceptance criteria. Check required create fields for all three types before the first write. If a required business value is missing, tell me which value is needed.

Give each record a stable marker in its description:
- asktd-planning:programme:AskTD
- asktd-planning:plan:P01
- asktd-planning:task:R1-A

Before creating each record, check for an existing match in ASKTD, including closed issues. Reuse a verified match with the correct type, scope, and parent. Stop on a conflicting or ambiguous match.

Create or reuse the Feature and read back its actual Jira key. Create the P01 Epic with that key in Parent Link (customfield_19601). Read the Epic back and verify that its stored Parent Link resolves to that exact Feature. If Jira rejects the parent, returns an empty field, or stores a different parent, stop there. Report the actual result and the keys already created. Do not create an unparented Epic as a fallback or substitute a generic issue link.

Only after the first relationship is verified, create R1-A as a Story with the actual P01 Epic key in Epic Link (customfield_10006). Read the Story back and verify its stored Epic Link.

If a write times out, search for its marker and reconcile the result before any retry. Keep new issues unassigned. Leave the planning package and Git unchanged. Stop after this one chain.

 For each record, show its clickable Jira URL, whether it was created or reused, and the parent key actually read back. Identify any step that remains unverified.
