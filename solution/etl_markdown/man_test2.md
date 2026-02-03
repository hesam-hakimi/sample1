# Copilot Prompt — Fix `edit_etl_config.py` “missing args” error (v2) + tests

> **Goal:** Fix the ETL Copilot VS Code extension so it *always* invokes `edit_etl_config.py` with the required CLI args `--file` and `--instruction`, on Windows, and add unit tests that prove the args are passed correctly.
>
> **Symptom (from screenshot):**
> `edit_etl_config.py: error: the following arguments are required: --file, --instruction`
>
> This happens when the extension spawns the Python script **without** those flags (or passes them in a way argparse can’t parse, e.g. as one big string).

---

## Step 0 — Read this before coding (required constraints)

1. **Do not change the Python CLI contract** of `edit_etl_config.py` unless absolutely necessary.
2. **Never call the Python script** if either:
   - `targetFilePath` is missing/empty, or
   - `instruction` is missing/empty.
   Instead return a user-facing message that explains what’s missing.
3. **Always pass args as an array** (tokens), not a single concatenated string.
   - ✅ `execFile(pythonExe, [scriptPath, "--file", filePath, "--instruction", instruction])`
   - ❌ `execFile(pythonExe, [scriptPath, "--file " + filePath + " --instruction " + instruction])`

---

## Step 1 — Locate the failing call site

Search the repo for the Python invocation and identify the exact function building/running the command:

- `edit_etl_config.py`
- `execFile(`, `spawn(`, `child_process`
- `python_modules/edit_etl_config.py` or similar

**You should end up with a TS/JS file like:**
- `src/applyEditHandler.ts` (or similar)
- `src/etlAssistantHandler.ts` (router/command registration)

### Verify Step 1
- In VS Code, open the file where the Python process is spawned.
- Confirm you can see code that calls `execFile`/`spawn` to run `edit_etl_config.py`.

---

## Step 2 — Make argument building pure + testable

Create a **pure helper** that builds argv tokens (no VS Code imports):

### Create `src/python/buildEditEtlArgs.ts`
- Export:
  - `buildEditEtlArgs(params): string[]`
  - `validateEditInputs(params): { ok: true } | { ok: false; reason: string }`

**Params should include:**
- `filePath: string`
- `instruction: string`
- Optional:
  - `mode?: string` (if your script supports it)
  - `preserveIncludes?: boolean | string` (match your script flags)
  - `asJson?: boolean` (if your script uses `--json`)

**Rules:**
- Always include: `["--file", filePath, "--instruction", instruction]`
- Only add option flags if you actually support them in Python:
  - `--mode <value>`
  - `--preserve-includes <value>` (or whatever your script expects)
  - `--json` (flag only)

### Verify Step 2
Add a **pure unit test** (plain mocha) that asserts:

- `buildEditEtlArgs({filePath:"C:\a\b.conf", instruction:"x"})`
  includes `--file` and `--instruction` and preserves spaces in `instruction` as one token.

---

## Step 3 — Fix the process invocation (the core bug)

Wherever you currently run the Python script:

1. Ensure you resolve:
   - `pythonExe` (e.g., `python`, `python3`, or configured setting)
   - `scriptPath` (absolute path to `edit_etl_config.py`)
   - `filePath` (absolute fsPath of the active/referenced editor file)
   - `instruction` (parsed from the chat request)

2. Call:
   - `const argv = [scriptPath, ...buildEditEtlArgs({ filePath, instruction, ...opts })];`
   - `execFile(pythonExe, argv, { cwd: repoRoot, windowsHide: true }, cb)`

3. **Do not run** if validation fails:
   - If file missing: return `"Open the ETL HOCON/JSON file to apply edits."`
   - If instruction missing: return `"Provide an apply instruction, e.g. apply: add data_sourcing ..."`

4. Add **debug logging** (behind a `debug` flag or output channel):
   - python exe
   - script path
   - argv tokens (string array)
   - exit code / stderr

> Important: if you currently use `shell: true` or `exec` with a single command string, replace with `execFile` + argv tokens.

### Verify Step 3
- Run your extension in the Extension Host.
- Trigger the apply flow.
- Confirm the output channel log shows argv like:
  - `python ... edit_etl_config.py --file <path> --instruction <text> ...`

---

## Step 4 — Fix instruction parsing so it’s never empty

Your chat prompt uses:
- `apply: add data_sourcing module reading parquet from ${source.srz.path}`

Make parsing robust:

- If the message contains `apply:` (case-insensitive), instruction is everything after `apply:`
- Else, instruction is the whole message (after trimming)
- Trim whitespace
- If the result is empty → validation error

### Verify Step 4
Add a pure test:

- Input: `"apply: add data_sourcing module ..."`
- Output: `instruction === "add data_sourcing module ..."`

---

## Step 5 — Add unit tests that prove the extension passes args

### A) Pure tests (plain mocha)
Create tests for:
- `buildEditEtlArgs`
- `parseApplyInstruction` (if you make it pure)
- `validateEditInputs`

### B) Extension-level test (VS Code test host) for execFile args
Because VS Code APIs require the Extension Test Host, do this:

1. Ensure your repo has a VS Code test harness:
   - `@vscode/test-electron`
   - `src/test/runTest.ts` and a suite loader in `src/test/suite/**`

2. Refactor your Python runner into an injectable function:
   - `runPythonEdit(pythonExe, scriptPath, argv, execFileImpl = execFile)`
   - In tests, pass a stub for `execFileImpl` that captures `pythonExe` and `argv`.

3. Write a test that:
   - Calls the handler with a fake filePath + instruction
   - Asserts execFile was called once with argv containing:
     - `scriptPath`
     - `"--file", filePath`
     - `"--instruction", instruction`

> This test ensures your real bug can’t come back.

### Verify Step 5
- `npm test` should run:
  - pure tests in node
  - VS Code extension tests in the test host
- The new tests must fail if `--file`/`--instruction` is missing.

---

## Step 6 — Make the user-facing behavior clearer

Update the “Edit failed” summary:

- If validation fails (missing file/instruction), do **not** show the Python usage.
- Show a clear next action:
  - “Open the ETL config file in the editor, then re-run.”
  - “Provide an instruction after `apply:`.”

Only show raw stderr if:
- You passed valid args and the script still failed.

### Verify Step 6
- Reproduce missing-file scenario and confirm the message is friendly (no Python usage dump).
- Reproduce valid scenario and confirm edits apply.

---

## Acceptance Criteria (must all be true)

1. Applying an instruction runs Python with argv tokens containing `--file` and `--instruction`.
2. Missing active/referenced file returns a friendly message and does **not** run Python.
3. Missing/empty instruction returns a friendly message and does **not** run Python.
4. Unit tests exist and assert argv correctness (including at least one test that would fail if args were concatenated).
5. `npm test` runs clean.

---

## If you still see the same error after this fix

Instrument and print the argv tokens. If argv does not include `--file` and `--instruction`, the problem is still in the TS arg builder.
If argv includes them, then the issue is likely:
- using the wrong `pythonExe` (different script invoked),
- wrong `scriptPath`,
- or arguments being dropped due to `shell: true` + quoting.

In all cases, **switch to `execFile` with argv tokens** and log the tokens.
