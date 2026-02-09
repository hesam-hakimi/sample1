We now have a runtime error in ETL Copilot:

"Error validating file: Error: command 'etlCopilot.validateActiveEtlFile' not found"

This means the extension calls vscode.commands.executeCommand("etlCopilot.validateActiveEtlFile") but the command is not registered (or the id mismatches package.json).

Task: Fix this in a robust way.

Requirements:
1) Search the repo for ALL occurrences of:
   - "validateActiveEtlFile"
   - "etlCopilot.validate"
   - vscode.commands.registerCommand(...)
   - contributes.commands in package.json

2) Make command IDs consistent:
   - If the intended command exists under a different id, update the caller to use the real id.
   - If it does not exist at all, implement it and register it.

3) Implement validateActiveEtlFile as a real command:
   - Add a command contribution in package.json:
     id: etlCopilot.validateActiveEtlFile
     title: ETL Copilot: Validate Active ETL File
   - Register it in activate() (extension.ts or etlAssistantHandler.ts—where commands are registered).
   - Implementation:
     a) Resolve active editor URI (or show friendly message and return ok=false)
     b) Determine file type (json/hocon) by extension or content
     c) For JSON: JSON.parse validation (with good error message)
     d) For HOCON: call existing python validate logic if available (or skip if not implemented) but do NOT crash.
     e) Return a structured result: { ok: boolean, filePath: string, fileType: string, message: string }

4) Caller-side change:
   - Wherever apply() calls validateActiveEtlFile, handle both cases:
     - If command exists, use it.
     - If for some reason it is still unavailable, fall back to a local validation function (same logic) instead of throwing.

5) Add a regression test:
   - Ensure activation registers 'etlCopilot.validateActiveEtlFile'
   - And calling apply does not throw even if validation fails.

6) After changes:
   - Run npm run compile
   - Run npm test
   - Ensure no other command IDs were broken.

Make minimal changes, keep backward compatibility.
Proceed by first locating existing commands and package.json contributions, then fix id mismatch or add missing command, then add test.
