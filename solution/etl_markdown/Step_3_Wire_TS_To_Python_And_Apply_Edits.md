# Step 3 — Wire TypeScript commands to Python + unit tests for applying edits

## Goal
Make `etlCopilot.applyEtlEditToActiveFile`:
1) Call `edit_etl_config.py`
2) Parse stdout JSON
3) Apply returned `updatedText` to the active document using `WorkspaceEdit`
4) Optionally show a diff preview (dry-run mode)

---

## Implementation checklist
1. **Create a helper module for python execution**
   - Create `src/pythonRunner.ts` exporting `runPythonJsonTool(...)`
   - This is crucial for testability (you can stub it in unit tests).
2. **Pass input safely**
   - Prefer stdin JSON to avoid command-line length limits
3. **Parse stdout**
   - Validate it is JSON
   - Require fields: `ok`, `updatedText`, `summary`
4. **Apply edit**
   - Create `WorkspaceEdit`
   - Replace entire document range (0..end)
   - `vscode.workspace.applyEdit(edit)`
5. **Save behavior**
   - Add setting: `etlCopilot.edit.autoSave` default `false`
   - If true, call `document.save()`
6. **Dry-run option**
   - Add setting: `etlCopilot.edit.dryRun` default `false`
   - If true, open a diff view and do not apply

---

## Unit tests for Step 3 (VS Code extension tests)

### Why you need the `pythonRunner` abstraction
Directly mocking `child_process.execFile` in compiled extension tests is brittle.
Instead:
- Wrap python execution in `pythonRunner.ts`
- In tests, stub `pythonRunner.runPythonJsonTool` to return controlled outputs.

### Tests to add
Create `src/test/commands.step3.test.ts` with:

1. **Applies updatedText to the document**
   - Create temp `etl_test.json` with known content
   - Open and make active
   - Stub pythonRunner to return:
     - `{ ok:true, updatedText:'{ "modules": { "x": 1 } }', summary:['...'] }`
   - Execute command
   - Assert the document text now equals `updatedText`

2. **Does not modify file if python fails**
   - Stub pythonRunner to throw an error (or return `ok:false`)
   - Execute command
   - Assert document text is unchanged

3. **Dry-run does not modify file**
   - Set config `etlCopilot.edit.dryRun=true` for test scope (or inject setting)
   - Stub pythonRunner success
   - Execute command
   - Assert document text unchanged
   - (Optional) assert diff command was invoked (avoid brittle checks; focus on “unchanged”)

4. **Auto-save behavior respects settings**
   - With `autoSave=false`, file remains dirty
   - With `autoSave=true`, file is saved (check `document.isDirty` after a small wait)

---

## Verification (must pass before Step 4)

### Run VS Code extension tests
```bash
npm test
```

### Run python tests (still must pass)
```bash
python -m pytest -q
```

### Expected results
- Step 3 tests pass:
  - content changes on success
  - unchanged on error/dry-run
- No Webviews are opened
