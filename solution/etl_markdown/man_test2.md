# Copilot Prompt: Restore `etlAssistantHandler.ts` behavior + fix `apply:` flow (Phase 4)

Paste this whole message into GitHub Copilot Chat **in the repo**, then let it make changes.

---

## Context

The recent changes to `src/etlassistanthandler.ts` (or `etlAssistantHandler.ts`) introduced **stub behavior**:
- `addReferencesToResponse` is a no-op
- the handler prints **“File edited …”** even when no edit happened
- `apply:` requests still end up with a useless summary like **“Instruction received …”** and do not reliably modify the active ETL JSON/HOCON file
- the handler got refactored heavily and lost the earlier behavior (documentation/tutorial routing, keyword-to-doc file loading, etc.)

**Goal:** restore the original behavior and implement Phase-4 correctly **without rewriting this file again**.

Follow `Meta_Testing_Strategy_For_Copilot.md` for the testing strategy.

---

## Step 0 — Get back the last-known-good handler (do this first)

1) Use git to locate a *working* version of the handler:
- `git log -- src/etlassistanthandler.ts`
- `git show <GOOD_COMMIT_SHA>:src/etlassistanthandler.ts`

2) Restore that version as the baseline (either full restore or selective revert):
- Preferred: `git checkout <GOOD_COMMIT_SHA> -- src/etlassistanthandler.ts`
- Or: `git restore -s <GOOD_COMMIT_SHA> -- src/etlassistanthandler.ts`

✅ Verify Step 0:
- The handler is back to the earlier structure (no dummy no-op functions, and the older routing logic is visible again).

---

## Step 1 — Make Phase-4 changes *minimal* and non-destructive

**Rule:** After restoring the baseline, only allow *small, surgical* changes to this file:
- DO NOT reorganize the whole handler
- DO NOT replace the prompt building strategy with a totally new one
- DO NOT add “always print File edited” logic

If a new capability is needed, implement it in **new helper modules**, then call them from the handler.

✅ Verify Step 1:
- `git diff src/etlassistanthandler.ts` shows only small deltas (ideally < ~40 lines changed).

---

## Step 2 — Fix apply intent detection (do NOT rely on `request.intent`)

In the current environment, `request.intent` may not be set the way you expect.

Implement intent detection as:

- `isApply = request.prompt.trim().toLowerCase().startsWith("apply:")`
- If `etlCopilot.chat.requireApplyKeyword` is true, only edit when `isApply` is true
- If it is false, you may infer edit intent, but still **never** edit on plain Q&A prompts

Also: strip `apply:` before sending the instruction to the apply command.

✅ Verify Step 2:
- Ask: `@etl_copilot what is data_sourcing module?` → **no file changes**
- Ask: `@etl_copilot apply: add data_sourcing module ...` → triggers edit pipeline

---

## Step 3 — Fix “File edited” reporting (only if edit really happened)

Change behavior:
- Only print “File edited: …” after the apply command returns `ok:true` **and** the document text changed.
- If apply fails or does not change text, print “Edit failed” / “No changes applied” and do not claim success.

✅ Verify Step 3:
- Force a failure (no active editor) → no “File edited”
- Successful apply → shows file edited + meaningful summary

---

## Step 4 — Fix the apply command path (the real problem)

Ensure `etlCopilot.applyEtlEditToActiveFile` is **implemented and registered**:

1) `package.json` includes it in `contributes.commands`
2) `activate()` registers it
3) the command:
   - reads active document
   - calls the Python editor / transformer
   - receives `{ ok, updatedText, summary }`
   - applies `updatedText` via `WorkspaceEdit` (replace full document)
   - returns a typed result

Use a shared type:

```ts
export type ApplyResult = {
  ok: boolean;
  filePath: string;
  summary: string[];
  changed?: boolean;
  error?: string;
};
```

✅ Verify Step 4:
- Open `tests/test.json` containing `{"modules":{}}`
- Run `@etl_copilot apply: add data_sourcing ...`
- Confirm the file now contains `"data_sourcing"` (or the HOCON equivalent)
- The summary contains at least 1 meaningful item, e.g. “Added modules.data_sourcing”

---

## Step 5 — Validation must run after apply and its output must be displayed

After a successful apply:
- Call `etlCopilot.validateActiveEtlFile`
- Show validation output (truncate if needed)
- If validation fails, still keep the applied changes, but report the failure.

✅ Verify Step 5:
- Break the JSON/HOCON on purpose, run apply, confirm validation shows an error message.

---

## Step 6 — Restore real reference injection for Q&A (no more generic answers)

Remove any stub / no-op reference logic.

Make sure Q&A prompts are built using:
- active file content (if JSON/HOCON)
- ETL framework docs from `src/context_files/**`
- keyword-based doc selection (like the earlier KEYWORD_FILE_MAP behavior)

If docs do not contain the answer, the assistant must say it cannot confirm rather than guessing.

✅ Verify Step 6:
- Ask: `@etl_copilot what is data_sourcing module?`
- Expected: answer quotes or clearly references your framework docs.

---

## Step 7 — Tests (VS Code Extension Test Host, not plain Mocha)

Add/Update tests using `@vscode/test-electron`:

### Test A — Apply edits change file
- open temp doc
- execute apply command
- assert doc includes `data_sourcing`
- assert ApplyResult.ok === true and summary.length > 0

### Test B — Q&A does not edit
- run Q&A path
- assert file unchanged

### Test C — Command is registered
- `vscode.commands.getCommands(true)` includes `etlCopilot.applyEtlEditToActiveFile`

✅ Verify Step 7:
- `npm test` passes in VS Code Extension Test Host.

---

## Deliverables

- Baseline handler restored from a known good commit (minimal edits only)
- `apply:` actually edits the open ETL JSON/HOCON file
- Summary shows what changed
- Validation runs and output is shown
- Q&A uses framework docs + active file context (no generic answers)
- VS Code extension host tests cover apply + Q&A behavior
