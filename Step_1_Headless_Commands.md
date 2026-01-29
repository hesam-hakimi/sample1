# Step 1 — Add headless VS Code commands (no Webview)

## Goal
Add command(s) to your ETL VS Code extension so it can **edit and validate ETL HOCON/JSON files without opening a Webview**. These commands will be called later from chat.

## Commands to implement
1. `etlCopilot.applyEtlEditToActiveFile`
2. `etlCopilot.validateActiveEtlFile`

## Requirements
- Work on the **active editor file** (fallback: `targetUri` passed to the command).
- Only allow ETL config formats: `.conf`, `.hocon`, `.json` (make this configurable).
- Guardrails:
  - Check `vscode.workspace.isTrusted` before modifying files.
  - Fail gracefully if no active editor file is open.

## Implementation checklist (do in order)
1. **Declare commands in `package.json`**
   - Add them under `contributes.commands`
   - Add keybindings only if needed (optional)
2. **Register commands in `activate(context)`**
   - `vscode.commands.registerCommand(...)`
3. **Implement argument handling**
   - `instruction: string`, `targetUri?: vscode.Uri` for apply
   - `targetUri?: vscode.Uri` for validate
4. **Resolve the target document**
   - If `targetUri` exists: `openTextDocument(targetUri)`
   - Else: `vscode.window.activeTextEditor?.document`
5. **Add file type checks**
   - Verify extension is in allowlist
   - If not allowed, return error (no edit)
6. **Stub behavior for now**
   - `applyEtlEditToActiveFile` can return a stub result (no python call yet)
   - `validateActiveEtlFile` can call existing `utils.py validate_config` if available; otherwise stub

## Output contract (return values)
Return structured results from commands:

- Apply:
```ts
{ ok: boolean, summary: string[], filePath: string }
```

- Validate:
```ts
{ ok: boolean, validationOutput: string, filePath: string }
```

## Verification (must pass before Step 2)
### Manual verification
1. Run Extension Development Host.
2. Open any `.json` file in the workspace.
3. Open Command Palette and run:
   - **ETL: Validate Active File** → should execute (even if stub).
   - **ETL: Apply Edit to Active File** → should execute (even if stub).
4. Confirm:
   - Commands appear in Command Palette
   - Commands do **not** open Webviews
   - If no active editor file, it shows a friendly error and does not crash

### Quick logging check
- Add minimal `console.log` (or output channel) to confirm the command runs and resolves the file path.
