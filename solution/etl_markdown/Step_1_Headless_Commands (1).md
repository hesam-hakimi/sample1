# Step 1 — Add headless VS Code commands (no Webview) + unit tests

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

---

## Implementation checklist (do in order)
1. **Declare commands in `package.json`**
   - Add them under `contributes.commands` with user-friendly titles:
     - “ETL: Apply Edit to Active File”
     - “ETL: Validate Active File”
2. **Register commands in `activate(context)`**
   - `vscode.commands.registerCommand(...)`
3. **Implement argument handling**
   - Apply: `{ instruction: string, targetUri?: vscode.Uri }`
   - Validate: `{ targetUri?: vscode.Uri }`
4. **Resolve the target document**
   - If `targetUri` exists: `openTextDocument(targetUri)`
   - Else: `vscode.window.activeTextEditor?.document`
5. **Add file type checks**
   - Verify extension is in allowlist
   - If not allowed, return `{ ok:false, ... }` and show a friendly error
6. **Stub behavior for now**
   - `applyEtlEditToActiveFile` may return a stub result (no python call yet)
   - `validateActiveEtlFile` may stub or call your existing `utils.py validate_config` if already available

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

---

## Unit tests for Step 1 (must implement now)

### Testing framework expectations
Use the standard VS Code extension test stack:
- `@vscode/test-electron`
- `mocha`
- Node `assert` (or `chai` if already used)

If your repo already has a test setup, **reuse it**.

### Tests to add (minimum)
Create `src/test/commands.step1.test.ts` (or similar) and include:

1. **Commands are registered**
   - After activation, `vscode.commands.getCommands(true)` includes:
     - `etlCopilot.applyEtlEditToActiveFile`
     - `etlCopilot.validateActiveEtlFile`

2. **Graceful behavior when no active editor**
   - Close all editors
   - Execute command `etlCopilot.applyEtlEditToActiveFile` with a dummy instruction
   - Expect `{ ok:false }` and a helpful message (assert on returned object; avoid brittle UI asserts)

3. **File type gate**
   - Open a temp file with `.txt`
   - Run apply command
   - Expect `{ ok:false }`

4. **Happy-path stub on supported file types**
   - Open a temp `.json` file
   - Run apply command
   - Expect it returns `{ ok:true }` OR `{ ok:false }` with a clear “not yet implemented” message
   - Key is: it must not crash and must resolve the file path correctly.

### How to create temp files in tests
- Create files under the test workspace folder during runtime (use `vscode.workspace.workspaceFolders[0].uri.fsPath`)
- Write file content using Node `fs`

---

## Verification (must pass before Step 2)

### Run unit tests
From extension root:
```bash
npm test
```

### Expected results
- Tests run successfully in VS Code Extension Test Host
- Command registration test passes
- No active editor test passes (no crash)
- `.txt` file rejected by file type check
