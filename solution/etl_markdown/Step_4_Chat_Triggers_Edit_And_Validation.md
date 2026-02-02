# Step 4 — Make chat participant trigger edits + validation + unit tests for intent + command calls

## Goal
When user chats with `@etl_copilot` in normal chat mode (no slash commands), the extension should:
- Detect explicit edit intent
- Apply changes to the active ETL config file
- Run validation
- Respond in chat with summary + validation output

---

## Implementation checklist
1. **Extract edit-intent detection into a pure function**
   - Example: `shouldApplyEdit(prompt: string, requireApplyKeyword: boolean): boolean`
   - This makes it unit-testable.
2. **In `etlAssistantHandler`**, when intent is true:
   - Call:
     - `vscode.commands.executeCommand("etlCopilot.applyEtlEditToActiveFile", { instruction: request.prompt })`
   - Then call:
     - `vscode.commands.executeCommand("etlCopilot.validateActiveEtlFile", { ... })`
3. **Stream a structured response**
   - Modified file path
   - Summary list
   - Validation output
4. **No active file behavior**
   - If no active editor doc, respond:
     - “Open the ETL HOCON/JSON file you want to edit and try again.”
5. **Safety toggle**
   - Setting: `etlCopilot.chat.requireApplyKeyword` default `true`
   - If true, only edit when prompt contains “apply:” (or similar)

---

## Unit tests for Step 4

### A) Pure unit tests (required)
Create `src/test/chat.intent.test.ts` to test `shouldApplyEdit(...)`:

Test cases:
- `"apply: add data_sourcing"` => true
- `"please add data_sourcing"` with requireApplyKeyword=true => false
- `"please add data_sourcing"` with requireApplyKeyword=false => true
- `"what is data_sourcing module?"` => false

### B) Handler integration test (recommended)
Make the handler testable by injecting dependencies:
- Extract internal side effects (executeCommand, stream.markdown) behind small interfaces.
- In tests, provide fakes that record calls.

Minimum integration assertions:
- When edit intent true:
  - handler calls `executeCommand` with apply command
  - then calls validate command
- When intent false:
  - handler does NOT call apply command
  - instead proceeds with normal model request flow (can be stubbed)

If full model mocking is too heavy, you can:
- Skip sending a real model request by passing a dummy model that returns a simple stream.

---

## Verification (must pass before Step 5)

### Run tests
```bash
npm test
python -m pytest -q
```

### Manual verification
1. Open `etl_test.json`
2. In Copilot Chat:
   - `@etl_copilot apply: add data_sourcing module reading parquet from ${source.srz.path}`
3. Confirm:
- File changes
- Validation runs
- Chat response summarizes changes + validation output

4. Ask informational question:
   - `@etl_copilot what is data_sourcing module?`
5. Confirm:
- No file change
