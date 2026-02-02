You are working on my VS Code extension “ETL Copilot” (chat participant `etl-extension.etl-copilot` / `@etl_copilot`).
Problem: In Phase 4, when I ask a framework question like “what is data_sourcing module?”, the assistant answers generically instead of using my ETL framework docs and the active ETL config file context. I need you to fix the handler so responses are grounded in project context.

Follow the Meta_Testing_Strategy_For_Copilot.md rules for tests.

### Step 1 — Identify why the response is generic
1) Inspect `etlAssistantHandler` and locate the branch that handles non-edit prompts (when intent is false).
2) Determine what context is being passed into the model (request.prompt only? is it missing file text and reference docs?).
3) Confirm whether we are using `request.references` and `vscode.ChatContext` properly.

✅ Verify Step 1:
- Add temporary logging to OutputChannel “ETL Copilot” to print:
  - active file path
  - whether edit intent triggered
  - how many references were detected/added
  - whether file content was included
- Run the extension and ask `@etl_copilot what is data_sourcing module?`
- Confirm logs show: active file path + references count + whether file content was injected.

### Step 2 — Add grounding context for Q&A
Implement a “context builder” used for BOTH:
- edit requests (apply:)
- informational Q&A requests

Context builder MUST:
- Read active editor file content (if allowed type: .json/.conf/.hocon)
- Add framework documentation context from `src/context_files/` (or the folder where our ETL docs live)
- Include a short “Framework Glossary / Rules” system instruction:
  - “Answer using the ETL framework docs first; if not found, say you can’t confirm and ask what module version/framework repo is used.”

Also add a setting:
- `etlCopilot.chat.grounding.enabled` default `true`
- `etlCopilot.chat.grounding.maxFileChars` default e.g. 12000 (truncate file content safely)

✅ Verify Step 2:
- Ask: `@etl_copilot what is data_sourcing module?`
- Expected: answer references the ETL framework docs content (module purpose, expected keys, example snippet) and relates it to current open config file if present.
- If docs do not contain it, it must say it can’t confirm and suggest where to look (file/module path) instead of guessing.

### Step 3 — Make intent detection prevent accidental edits, but still allow grounded answers
Keep `requireApplyKeyword` behavior:
- Only modify files when prompt starts with `apply:` (or configured keyword).
- For non-apply prompts, NEVER modify file — only read and answer.

✅ Verify Step 3:
- Ask: `@etl_copilot apply: add data_sourcing ...` => file changes + validation runs.
- Ask: `@etl_copilot what is data_sourcing module?` => NO file change + grounded answer.

### Step 4 — Add tests so this never regresses
Create VS Code extension host integration tests that validate grounding behavior:

Test A (Q&A does not edit file):
- Open a temp `etl_test.json` as active editor
- Call handler (or command path) with prompt “what is data_sourcing module?”
- Assert: file content unchanged

Test B (Q&A includes framework context):
- Put a small fake doc in `src/context_files/data_sourcing.md` during test setup (or use an existing doc)
- Call handler prompt “what is data_sourcing module?”
- Assert: returned chat output includes a phrase from that doc (or a keyword), proving it used the docs

Test C (Apply edits):
- Existing apply tests should still pass

✅ Verify Step 4:
- Run `npm test` (VS Code host test) and ensure all pass.

### Step 5 — Improve the UX response formatting
For Q&A responses, format output like:
- “From ETL Framework Docs:” + bullet points
- “In your current file:” + mention whether module exists / missing keys
- “Example config snippet:” (short)

✅ Verify Step 5:
- Manual run in VS Code: ask the question again and confirm output has these sections and is not generic.
