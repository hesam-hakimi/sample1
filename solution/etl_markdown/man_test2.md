Fix Phase 4: ETL Copilot says “Open the ETL HOCON/JSON file to apply edits” even when a file reference chip (e.g., test.json) is attached in Copilot Chat.

Root cause: handler likely uses only vscode.window.activeTextEditor and ignores request.references.

Requirements:
- If a file reference is attached in the chat request, use it as the target file (highest priority).
- If no reference, fallback to active editor.
- If neither exists, THEN show the “open file” message.
- Keep backward compatibility (same command IDs, participant ID, settings keys).
- Follow Meta_Testing_Strategy_For_Copilot.md for tests (VS Code extension host, not plain mocha).

Implement:
1) Add resolveTargetUri(request): vscode.Uri | undefined
   - Iterate request.references (log them for debugging).
   - Pick the first reference that is a vscode.Uri (or has a URI you can parse).
   - Fallback: activeTextEditor?.document.uri

2) If targetUri exists but the file isn’t open, open it:
   - const doc = await vscode.workspace.openTextDocument(targetUri)
   - (optional) await vscode.window.showTextDocument(doc, { preview: false })

3) Pass targetUri into apply + validate commands:
   - executeCommand("etlCopilot.applyEtlEditToActiveFile", { instruction, targetUri })
   - executeCommand("etlCopilot.validateActiveEtlFile", { targetUri })

4) Improve the user response:
   - Always print: Target file: <path> and whether it came from reference vs active editor.

Tests (VS Code Extension Host):
- Test A: No active editor + provide a targetUri to command -> file gets edited
- Test B: Handler uses reference file when active editor is absent
- Test C: If no reference and no active editor -> returns the “Open file” message

Verification:
- npm test passes
- Manual: with editor closed, attach test.json chip and run apply -> it edits test.json
