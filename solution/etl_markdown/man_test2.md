# Copilot prompt — Fix `edit_etl_config.py` “missing args” error (Phase 4)

Use this prompt **as-is** in GitHub Copilot Chat (in the repo root). It tells Copilot exactly how to fix the bug and how to prove it’s fixed.

---

## Context (what’s broken)

When the user runs:

`@etl_copilot apply: add data_sourcing module reading parquet from ${source.srz.path}`

the extension calls the Python CLI `edit_etl_config.py` **without** required flags, so Python prints:

- `error: the following arguments are required: --file, --instruction`

That means the VS Code extension is spawning Python incorrectly (or spawning it even when it failed to resolve the target file/instruction).

---

## Your task

### Step 1 — Find where Python is invoked
1. Search for **all** references to `edit_etl_config.py` and to the function that runs python (e.g. `spawn`, `exec`, `execFile`).
2. Identify the call path from the command handler (likely `etlAssistantHandler.ts` → `applyEditHandler.ts`) to the Python invocation.

✅ **Verify (Step 1)**  
Add a temporary debug log (or return in the chat summary) that prints:
- resolved target file path (if any)
- resolved instruction (first ~80 chars)
- the args array passed to Python (sanitized)

Run `npm run compile` and ensure there are **no TypeScript errors**.

---

### Step 2 — Enforce a single “args builder” for the Python CLI
Create a small pure function (new file is OK), e.g.:

- `src/core/pythonArgs/buildEditEtlConfigArgs.ts`

It must accept:
- `targetFilePath: string`
- `instruction: string`
- options: `{ mode?: string; preserveIncludes?: boolean; asJson?: boolean }`

It must return an **array of args** that matches the Python CLI help exactly:

- `--file <targetFilePath>`
- `--instruction <instruction>`
- optional:
  - `--mode <mode>` (ONLY if mode provided)
  - `--preserve-includes <true|false>` (or the exact format your argparse expects)
  - `--json` (ONLY if editing JSON or you explicitly want JSON output)

Important:
- Use `spawn` / `execFile` with an args array. **Do not** build a single shell string.
- If either `targetFilePath` or `instruction` is empty, throw a typed error (e.g. `MissingArgsError`) so the caller can show a friendly message and **skip** spawning Python.

✅ **Verify (Step 2)**  
Add a unit test for the args builder (plain mocha is fine because it’s pure logic):

- `src/test/unit/buildEditEtlConfigArgs.test.ts`

Test cases:
1. JSON file path + instruction → args includes `--file` and `--instruction` with exact values, and includes `--json` when `asJson: true`.
2. Missing file path → throws `MissingArgsError`
3. Missing instruction → throws `MissingArgsError`

Run:
- `npm run compile`
- `npm test` (unit tests only)

---

### Step 3 — Wire the args builder into the actual handler
In the handler that currently calls Python (likely `applyEditHandler.ts`):
1. Ensure you **resolve** the target file first:
   - prefer active editor text document
   - else accept a file reference path (if your chat provides one)
2. Ensure you extract the **instruction** text from the apply prompt (trim, preserve punctuation)
3. Call `buildEditEtlConfigArgs(...)`
4. Invoke python using `execFile` or `spawn`:

Example shape (don’t copy blindly; fit your codebase):
- `execFile(pythonExe, [scriptPath, ...args], { cwd: workspaceRoot })`

5. If you catch `MissingArgsError`, return a user-friendly summary like:
   - “Open an ETL HOCON/JSON file and re-run apply.”
   - and include what was missing (file or instruction)

✅ **Verify (Step 3)**  
Add a **VS Code Extension Host** test (must use `@vscode/test-electron`, not plain mocha):

- Open a temp JSON document in the test host
- Trigger the command that handles `apply`
- Stub/mock the python runner so it doesn’t really run python
- Assert the runner was called with args containing `--file <openedDocPath>` and `--instruction <expectedInstruction>`

Run:
- `npm run compile`
- `npm test` (extension host tests)

---

### Step 4 — Add a regression test for the exact failure
Create an integration-style test that reproduces the current bug:
- simulate calling apply while no active editor is open (or no target doc resolved)
- assert:
  - python runner is NOT invoked
  - summary returns “Open the ETL HOCON/JSON file to apply edits.”

✅ **Verify (Step 4)**  
Run `npm test` and confirm the regression test passes.

---

### Step 5 — Manual verification (what I will do after your change)
After tests pass, I will manually:
1. Open `test.json` in the editor
2. Run: `@etl_copilot apply: add data_sourcing module reading parquet from ${source.srz.path}`
3. Expect:
   - No “missing args” Python usage output
   - Summary shows either:
     - changes applied, or
     - “no changes applied” **with a reason** (e.g., parser couldn’t find insertion point)

If it still fails, your summary must include:
- resolved file path
- detected file type (json/hocon)
- the python args list (sanitized)
so we can debug fast.

---

## Non-negotiables
- Do **not** call python if file path or instruction is missing.
- Use `execFile`/`spawn` with args array (no shell string).
- Add tests (pure unit + extension host) so this never regresses.

---
