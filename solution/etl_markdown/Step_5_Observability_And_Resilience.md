# Step 5 — Observability + resilience + unit tests for failure paths and rollback

## Goal
Make the extension production-ready:
- Detailed logging
- Clear error handling
- No file corruption on failures
- Optional rollback

---

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
3. **Rollback support (recommended)**
   - Store last pre-edit content in memory (per session)
   - Provide command: `etlCopilot.undoLastEdit`
   - Only works for last edit in current session
4. **Secret hygiene**
   - Never log tokens
   - If python prints tokens, sanitize stderr/stdout before logging

---

## Unit tests for Step 5

Create `src/test/resilience.step5.test.ts` with:

1. **Logs are written on error**
   - Force pythonRunner to throw
   - Execute apply command
   - Assert:
     - file unchanged
     - output channel received an error line (implement output channel wrapper so it can be asserted)

2. **Rollback restores previous content**
   - Stub pythonRunner success returning modified content
   - Execute apply command
   - Execute undo command
   - Assert document content equals original

3. **Validation failure is reported but does not crash**
   - Stub validate command to return `{ ok:false, validationOutput:'...' }`
   - Ensure apply still returns a structured result and handler reports validation failure

> Tip: for testability, wrap output channel write calls in a small logger interface and inject a fake in tests.

---

## Verification (must pass before Step 6)

### Run tests
```bash
npm test
python -m pytest -q
```

### Manual verification
1. Force python failure (temporary)
2. Run edit from chat/command
3. Confirm:
- File unchanged
- Error message shown
- Logs written in “ETL Copilot” output channel

4. Apply an edit successfully, then run undo
5. Confirm:
- File content restored
