# Step 6 — Documentation + examples + test runner scripts

## Goal
Make the feature easy for your team to use and easy to verify in CI:
- Explain how to edit configs from Copilot Chat
- List supported file types
- Provide example prompts
- Explain settings (dryRun, autoSave, requireApplyKeyword)
- Add scripts to run **all tests** (TypeScript + Python)

---

## README updates
Add sections:
1. **What it does**
   - “Edit ETL framework HOCON/JSON configs from Copilot Chat”
2. **Prerequisites**
   - Workspace trust
   - Python available on PATH
   - Required python libs (e.g., pyhocon if used)
3. **How to use**
   - Open ETL config file
   - Ask `@etl_copilot` with explicit “apply:”
4. **Examples**
   - “apply: add data_sourcing module reading parquet from SRZ”
   - “apply: change writer path to …”
   - “apply: add transformation step …”
5. **Commands**
   - ETL: Apply Edit to Active File
   - ETL: Validate Active File
   - ETL: Undo Last Edit (if implemented)
6. **Settings**
   - `etlCopilot.edit.dryRun`
   - `etlCopilot.edit.autoSave`
   - `etlCopilot.chat.requireApplyKeyword`
7. **Troubleshooting**
   - Python missing
   - Parser missing
   - Validation failures

---

## Add unified test scripts (recommended)
In `package.json`, add scripts:
- `test:ts` → existing extension host tests (`npm test` or equivalent)
- `test:py` → `python -m pytest -q`
- `test:all` → run both

Example:
```json
{
  "scripts": {
    "test:ts": "npm test",
    "test:py": "python -m pytest -q",
    "test:all": "npm run test:ts && npm run test:py"
  }
}
```
(Adapt to your repo’s existing scripts; avoid recursion if `npm test` already runs.)

---

## Verification

### Run all tests locally
```bash
npm run test:all
```

### Expected results
- Extension tests pass
- Pytest tests pass
- README instructions work in a fresh Extension Dev Host run
