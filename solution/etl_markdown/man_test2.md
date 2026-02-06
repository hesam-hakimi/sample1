You are working inside a VS Code extension repo (ETL Copilot). Fix the apply command end-to-end.

Context:
- The apply command routes through etlAssistantHandler.ts -> applyEditHandler.ts (and shouldApplyEdit.ts).
- apply ultimately calls a python CLI: src/python_modules/edit_etl_config.py
- Current failures:
  1) If user runs apply without an active editor or without a file, the extension calls python without required args -> error: required: --file, --instruction.
  2) If user opens an empty JSON {} and runs apply, the file is actually updated on disk, but VS Code doesn’t reflect changes (shows “Failed to save… file is newer”) and the extension throws: applyResult.summary.join is not a function.
  3) Sometimes python output shows JSON parse error “Expecting value line 1 col 1/ line 2 col 1” (likely because extension passed empty/invalid text or wrong file).

Goal:
Make apply reliable for JSON + HOCON and keep the VS Code editor in sync. No breaking changes.

Implement these changes:

A) Robust target file resolution (must never call python without required args)
- In applyEditHandler.ts create/ensure a single function resolveTargetUri(request|context):
  - Prefer the active text editor document URI if it exists.
  - Else if the command is invoked with a URI argument (context menu), use that.
  - Else show a user-friendly error message and STOP:
    "Open an ETL HOCON/JSON file (or right-click a file and choose Apply) and try again."
- Pass that resolved path to python as --file ALWAYS.

B) Guarantee instruction is always provided
- The instruction comes from the chat input. Ensure applyEditHandler receives a non-empty string.
- If empty/whitespace: show error "Instruction is required" and STOP.

C) Standardize apply result type to fix `.summary.join is not a function`
- Define a strict TypeScript type in a shared file (e.g., src/types/applyResult.ts):
  type ApplyResult = {
    ok: boolean;
    changed: boolean;
    filePath: string;
    fileType: "json" | "hocon" | "unknown";
    summary: string[];          // ALWAYS array
    error?: string;             // present when ok=false
    stderr?: string;
    stdout?: string;
  };
- Update all code paths so summary is always string[].
  - If you currently build summary as a string, wrap it: [summaryString]
  - If python returns summary as string, normalize to [string]
  - If missing, default to [].
- Replace any direct `.summary.join(...)` usage with a safe join:
  const summaryText = applyResult.summary.length ? applyResult.summary.join("\n") : "(no summary)";
- Add runtime guards (since python output is untyped):
  function normalizeApplyResult(raw: any, fallbackFilePath: string): ApplyResult { ... }

D) Fix editor sync and the “file is newer / compare / overwrite” problem
This happens because python edits the file on disk while the editor has a stale buffer (or is dirty).
Implement this policy:
- If the target document is currently open AND is dirty (has unsaved changes):
  - Prompt user: "The file has unsaved changes. Save before applying edits?" with buttons [Save & Apply] [Cancel]
  - If Save & Apply: await document.save()
  - If Cancel: STOP.
- After python finishes successfully (or even if it reports changed=true):
  - If the file is open in an editor, force VS Code to reload it from disk:
    await document.save() is not enough because disk changed externally.
    Use: await document.revert() (preferred) OR close+reopen document programmatically:
      const doc = await vscode.workspace.openTextDocument(uri);
      await vscode.window.showTextDocument(doc, { preview: false });
  - Ensure this prevents the “file is newer” toast when user later saves.
- Also: avoid writing to the file via both python AND WorkspaceEdit. Choose ONE:
  - Keep python as the writer, but ALWAYS revert/reload the open editor after python writes.
  - Do NOT do a second write from TypeScript if python already wrote.

E) Improve python error reporting (so we see the real cause, not generic “Python tool failed”)
- In the Node/TS layer that spawns python, capture stdout and stderr separately.
- If python exits non-zero:
  - Include stderr in ApplyResult.error and show it in the chat summary.
  - Truncate long stderr to e.g. last 40 lines.
- If python returns JSON parse error:
  - Add a specific hint:
    "The file content is not valid JSON. If this is HOCON, run with HOCON mode or enable HOCON parsing. If the file is empty, add at least {}."

F) Handle empty JSON {} properly
- Ensure the extension reads the active editor’s file type based on extension OR content, but do not assume HOCON is JSON.
- If file is JSON and content is exactly {} (valid), it must not cause applyResult.summary to break.
- The apply operation should either:
  - Add the requested module into modules.* and set changed=true, or
  - Return ok=true, changed=false, with a clear reason in summary (array).

G) Add/Update tests
- Add tests that cover:
  1) apply with no active editor and no URI -> must not run python; returns ok=false; shows friendly message.
  2) apply with active editor containing {} -> runs python with correct args; does not throw; summary is array; no join crash.
  3) apply when editor dirty -> prompts Save & Apply; on save continues.
  4) after apply changed=true and file open -> document is reverted/reloaded (simulate by checking that the extension calls revert or reopen path in code via stubs).
- Use vscode-test-electron for extension tests (not plain mocha importing vscode).

Deliverables:
- Code changes in:
  - src/applyEditHandler.ts (or wherever apply logic lives)
  - src/etlAssistantHandler.ts (routing)
  - src/types/applyResult.ts (new)
  - any python runner wrapper file
  - tests folder
- Ensure `npm run compile` and `npm test` pass.

Important:
- Keep backward compatibility: existing commands and behavior should remain, but fixed.
- Do not change python CLI interface; adapt TypeScript to pass correct args and normalize outputs.
Proceed step-by-step: implement types + normalization, then target resolution, then editor sync, then tests.
