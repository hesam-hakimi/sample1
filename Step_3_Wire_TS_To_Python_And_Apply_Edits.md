# Step 3 — Wire TypeScript commands to Python and apply edits to the active file

## Goal
Make `etlCopilot.applyEtlEditToActiveFile`:
1) Call `edit_etl_config.py`
2) Parse stdout JSON
3) Apply returned `updatedText` to the active document using `WorkspaceEdit`
4) Optionally show a diff preview (dry-run mode)

## Implementation checklist
1. **Create a helper function** for python execution
   - Use `execFile("python", ...)`
   - Set `maxBuffer` large enough (configs can be big)
2. **Pass input safely**
   - Prefer stdin JSON to avoid command-line length limits
3. **Parse stdout**
   - Validate it is JSON
   - Require fields: `ok`, `updatedText`, `summary`
4. **Apply edit**
   - Create `WorkspaceEdit`
   - Replace entire document range (0..end)
   - Apply edit: `vscode.workspace.applyEdit(edit)`
5. **Save behavior**
   - Add setting: `etlCopilot.edit.autoSave` default `false`
   - If true, call `document.save()`
6. **Dry-run option**
   - Add setting: `etlCopilot.edit.dryRun` default `false`
   - If true, open a diff view and do not apply

## Recommended user experience
- On success: show info message with summary
- On failure: show error message and log details to Output Channel

## Verification (must pass before Step 4)
### Happy path
1. Create file `etl_test.json`:
```json
{ "modules": {} }
```
2. Open it in editor.
3. Run command:
   - “ETL: Apply Edit to Active File”
   - Instruction: “Add module data_sourcing with type file and format parquet”
4. Confirm:
- File content changes (or diff opens if dryRun)
- No Webview opens
- Summary is shown

### Dry-run path
1. Set `etlCopilot.edit.dryRun = true`
2. Run the same command
3. Confirm:
- A diff view opens
- Original file is unchanged

### Failure path
1. Break python script or pass invalid input
2. Confirm:
- File is unchanged
- Error displayed
- Error logged to output channel
