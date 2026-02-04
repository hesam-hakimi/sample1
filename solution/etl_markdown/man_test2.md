# Copilot Prompt — Fix “Python tool failed: Command failed … edit_etl_config.py …” (show real stderr + safe args + tests)

> Copy/paste this whole prompt into **GitHub Copilot Chat** (in your ETL Copilot extension repo).  
> Goal: make the “apply:” command reliably invoke `edit_etl_config.py`, preserve `${...}` placeholders, and **surface real Python stderr** so failures are diagnosable. Also add tests so we don’t regress.

---

## Context (what’s broken)

The chat UI currently shows:

- `Edit failed. Summary: [ERROR] Python tool failed: Python error. Command failed: python ... edit_etl_config.py --file ... --instruction ... --mode apply --preserve-includes true --json`
- But it **does not show the actual stderr** from Python (traceback / module not found / parse error).
- On Windows, if the extension uses `exec(..., { shell: true })` or runs through PowerShell, strings like `${source.srz.path}` can be interpreted by the shell. Even if it *looks* fine in logs, it can break in subtle ways.
- Also, if args are passed as a single string, `--instruction` can be split into multiple args, causing `argparse` failures (you already hit missing `--file/--instruction` earlier).

---

## Success criteria

After the change:

1. The TS side calls Python using **args array** (NOT a single command string), with **shell disabled**.
2. On failure (non‑zero exit code), the extension returns a chat summary that includes:
   - exit code
   - the exact python path + script path (sanitized)
   - **captured stderr** (first/last N lines)
3. `${source.srz.path}` stays literal and reaches Python unchanged.
4. Unit tests assert the arg list and error surfacing behavior.
5. `npm run compile` and `npm test` pass.

---

## Step 1 — Locate the Python runner and make invocation “args-array + shell:false”

**Task**
- Find the code that runs Python (likely in `applyEditHandler.ts`, `etlAssistantHandler.ts`, or a helper like `pythonRunner.ts`).
- Replace any `exec("python ...")` / `spawn("python ...", { shell: true })` usage with `execFile` or `spawn` using an **args array** and **shell: false**.

**Implementation notes**
- Prefer `child_process.execFile`:
  - `execFile(pythonExe, [scriptPath, ...args], { shell: false, cwd, env })`
- If you use `spawn`, do:
  - `spawn(pythonExe, [scriptPath, ...args], { shell: false, cwd, env })`

**Verification**
- Add a temporary debug log that prints:
  - `pythonExe`, `scriptPath`, and `args` array (not a joined string)
- Run `npm run compile` — must pass.

---

## Step 2 — Centralize “buildPythonArgs()” so tests can assert it

**Task**
Create a function that builds arguments deterministically, e.g.

- `buildEditEtlArgs({ filePath, instruction, mode, preserveIncludes, asJson }): string[]`

It must return something like:

- `["--file", "<path>", "--instruction", "<instruction>", "--mode", "apply", "--preserve-includes", "true", "--json"]`

**Important**
- `instruction` must be a **single element** in the args array (it can contain spaces).
- Do not join args into a single string anywhere.
- Do not use `shell: true`.

**Verification**
- Add a small unit test that checks:
  - `args.includes("--file")` and the next element is the file path
  - `args.includes("--instruction")` and the next element equals the full instruction string
  - `${source.srz.path}` appears exactly in the instruction arg value

---

## Step 3 — Capture stdout/stderr and return a useful error message to the chat UI

**Task**
Update the Python runner to collect outputs:

- If exit code === 0:
  - parse stdout as JSON (or treat stdout as the updated file content depending on your contract)
- Else:
  - include stderr in the error summary

**Recommended behavior**
- Capture `stdout` and `stderr` as strings.
- In the chat response, include:
  - `exitCode`
  - `stderr` (truncate: first 60 lines + last 60 lines)
  - optionally include `stdout` if helpful

**Verification**
- Unit test:
  - stub `execFile`/`spawn` to simulate exit code 1 with `stderr="Traceback ..."`
  - assert the returned summary contains `Traceback` (or at least a substring)

---

## Step 4 — Make Python fail loudly (stderr) and exit non‑zero

**Task**
Open `src/python_modules/edit_etl_config.py` and ensure:

- All exceptions print a helpful message to **stderr**
- The process exits with `sys.exit(1)` on failures
- On success, prints a well‑formed JSON object to stdout (e.g., `{ "ok": true, ... }`)

**Verification**
- Run the exact command from the UI manually in terminal, but **quote the instruction**:
  - PowerShell: use single quotes to keep `${...}` literal  
    `python ... edit_etl_config.py --file ... --instruction 'add ... from ${source.srz.path}' --mode apply --preserve-includes true --json`
- Confirm:
  - Success prints JSON to stdout
  - Failure prints traceback / error details to stderr

---

## Step 5 — Fix the chat “No changes applied” vs “Edit failed” flow

**Task**
In `applyEditHandler()`:
- Distinguish between:
  - Python failure (exit code != 0) => “Edit failed” + stderr excerpt
  - Python success but no diff => “No changes applied” + reason code (e.g., `NO_MATCH`, `PARSE_OK_NO_OP`)
  - Python success and changed => “Applied changes” + summary (what changed)

**Verification**
- Add tests for the three cases (success-changed, success-noop, failure).

---

## Step 6 — Add the right tests (pure logic + extension-host only where needed)

### 6A) Pure TS unit tests (run under mocha without VS Code host)
Create tests that do NOT import `vscode`.

- `buildEditEtlArgs` tests (arg list correctness)
- `pythonRunner` tests (stderr surfaced on failure)
- `shouldApplyEdit` tests if you have logic there

### 6B) VS Code extension tests (only for command registration / editor interaction)
If you need to test `vscode.commands.executeCommand(...)`, use `@vscode/test-electron`.

- Ensure `npm test` runs in Extension Test Host (not plain mocha).
- Keep these tests minimal: “command is registered” + “returns friendly error when no active editor”.

**Verification**
- `npm run compile`
- `npm test`
- In Extension Development Host (F5), open `tests/test.json`, run:
  - `@etl_copilot apply: add data_sourcing module reading parquet from ${source.srz.path}`
- Confirm:
  - if python fails, you see stderr in the chat response

---

## Step 7 — Important dev workflow check (avoid running the installed extension by mistake)

Your error screenshot shows Python running from:

- `c:\Users\<you>\.vscode\extensions\etlfw-team.etl-copilot-0.1.3\...`

That usually means you’re executing the **installed** extension, not your local dev build.

**Task**
- Run the extension via **Extension Development Host** (F5) and confirm logs show:
  - `Loading development extension at <your repo path>`

**Verification**
- In dev host, the Python script path should be under your repo (or `.vscode-test`), not the installed extension folder.

---

## Deliverables (what I expect you to change)

1. A TS helper that builds python args (testable).
2. A TS python runner that:
   - uses `execFile`/`spawn` with args array
   - captures stdout/stderr
   - returns structured result `{ ok, stdout, stderr, exitCode }`
3. `applyEditHandler` updated to:
   - call python runner with correct args
   - show meaningful error summaries
4. Unit tests for args + stderr surfacing.
5. If needed, minimal VS Code extension-host tests using `@vscode/test-electron`.

When done, run:
- `npm run compile`
- `npm test`

and paste the results + the updated error output (if any).
