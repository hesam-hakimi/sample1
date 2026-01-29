# Step 5 — Add observability and resilience

## Goal
Make the extension production-ready:
- Detailed logging
- Clear error handling
- No file corruption on failures
- Optional rollback

## Implementation checklist
1. **Output Channel**
   - Create `vscode.window.createOutputChannel("ETL Copilot")`
   - Log:
     - command invocation
     - target file path
     - python script path
     - timing
     - stdout/stderr snippet (redact secrets)
2. **Failure handling**
   - If python fails: do not edit file; show error + log
   - If validation fails: report failure + show validation output
3. **Rollback support (optional but recommended)**
   - Store last pre-edit content in memory
   - Provide command: `etlCopilot.undoLastEdit`
   - Only for current session
4. **Secret hygiene**
   - Never log tokens
   - If your python prints tokens, sanitize stderr/stdout before logging

## Verification (must pass before Step 6)
1. Force python error:
   - rename python script temporarily or throw exception
2. Run edit command
3. Confirm:
- File content unchanged
- Error shown in UI
- Details in Output Channel

4. Force validation failure:
   - Make config invalid intentionally
5. Run edit
6. Confirm:
- Edit applied OR not (depending on design)
- Validation output shown
- Output channel has details
