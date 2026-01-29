# Step 4 — Make the chat participant trigger edits and validation

## Goal
When user chats with `@etl_copilot` in normal chat mode (no slash commands), the extension should:
- Detect edit intent
- Apply changes to the active ETL config file
- Run validation
- Respond in chat with summary + validation output

## Implementation checklist
1. **In `etlAssistantHandler`**, detect edit intent only when explicit.
   - Examples: “add module”, “update config”, “edit hocon”, “change writer”, “apply changes”
   - Avoid triggering on informational questions (“what is data_sourcing?”)
2. **If edit intent**
   - Call:
     - `vscode.commands.executeCommand("etlCopilot.applyEtlEditToActiveFile", { instruction: request.prompt })`
   - Then call:
     - `vscode.commands.executeCommand("etlCopilot.validateActiveEtlFile", { ... })`
3. **Stream a structured response**
   - What file was modified
   - Summary list from edit
   - Validation output
4. **No active file behavior**
   - If no active editor doc, respond:
     - “Open the ETL HOCON/JSON file you want to edit and try again.”
5. **Safety toggle (recommended)**
   - Setting: `etlCopilot.chat.requireApplyKeyword` default `true`
   - Only edit if user includes a keyword like “apply” / “make the change”

## Verification (must pass before Step 5)
1. Open `etl_test.json` in editor.
2. In Copilot Chat:
   - `@etl_copilot apply: add data_sourcing module reading parquet from ${source.srz.path}`
3. Confirm:
- The file changes
- Chat responds with summary + validation output
4. Close the file (no active editor)
5. Ask the same question again
6. Confirm:
- No crash
- Chat responds with “open a file” guidance
