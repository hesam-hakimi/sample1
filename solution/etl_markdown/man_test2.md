# Fix Prompt for Copilot: `edit_etl_config.py` missing `--file` / `--instruction`

You’re seeing this error:

> `edit_etl_config.py: error: the following arguments are required: --file, --instruction`

That means the VS Code extension is invoking the Python CLI **without the required flags**, even though your chat command includes the instruction text.

Use the prompt below in **GitHub Copilot Chat inside the repo** (so it can edit the code).

---

## Copilot Prompt (copy/paste)

You are working in this VS Code extension repo.

**Goal:** Fix the `apply:` flow so it correctly calls `src/python_modules/edit_etl_config.py` with the required CLI flags `--file` and `--instruction`, and preserves HOCON `include` lines.

### Step 1 — Find the call site
1. Search for where the extension executes Python for apply edits.
   - Look for `edit_etl_config.py`, `execFile("python"`, `spawn("python"`, or helper wrappers like `executePython...`.
2. Identify the exact TypeScript function that handles the chat command `apply:` (likely `applyEditHandler.ts` or a branch inside `etlAssistantHandler.ts`).

✅ Verify:
- You can point to the exact TS file + function where `edit_etl_config.py` is invoked.

---

### Step 2 — Standardize how we build Python args
1. Create a small helper (or update existing) that builds args for `edit_etl_config.py`:

**Required behavior**
- Always pass:
  - `--file <absolute-or-workspace-resolved-path>`
  - `--instruction <full instruction string>`
- Also pass:
  - `--preserve-includes true` (or `1`) to keep `include "..."` lines
  - If the CLI supports it, pass `--mode apply` (or omit if not supported)
  - Only pass `--json` when the target file is JSON (e.g. `.json` extension)

**Example invocation**
```ts
const args = [
  scriptPath,
  "--file", targetFilePath,
  "--instruction", instruction,
  "--preserve-includes", "true",
];

if (mode) args.push("--mode", mode);
if (isJsonFile) args.push("--json");
```

2. Ensure we do **NOT** build a single command string that needs shell parsing.
   - Use `execFile`/`spawn` with an args array.

✅ Verify:
- Add a temporary `console.log("edit_etl_config args:", args)` and confirm it prints both `--file` and `--instruction` before executing.
- Run `npm run compile` successfully.

---

### Step 3 — Fix target file resolution (so `--file` is never empty)
1. Ensure `targetFilePath` is resolved from:
   - Active editor file path **or**
   - A referenced file (if your design supports that)
2. If no file can be resolved, return a clear message:
   - `"Open the ETL HOCON/JSON file to apply edits."`
   - and do NOT call python.

✅ Verify:
- Run the apply command with no editor open → you get that message (and no python call).
- Open a JSON/HOCON file and run apply → python is called with a real `--file` path.

---

### Step 4 — Fix instruction extraction (so `--instruction` is never empty)
1. Confirm the handler extracts the raw instruction string **after** `apply:` exactly as entered.
   - Example: `apply: add data_sourcing module reading parquet from ${source.srz.path}`
2. Do **NOT** split on `|` or whitespace in a way that drops the instruction.

✅ Verify:
- Add a temporary `console.log("instruction:", instruction)` and confirm it matches the message text after `apply:`.
- Re-run the command and confirm python receives a non-empty `--instruction`.

---

### Step 5 — Make the result type safe (avoid `(applyResult as any)?.ok`)
1. Define a TS type for python results (even if python returns plain text):
```ts
type ApplyEditResult =
  | { ok: true; changed: boolean; summary: string; newText?: string }
  | { ok: false; summary: string; error: string };
```
2. Parse python stdout safely:
   - If stdout is JSON → `JSON.parse` into `ApplyEditResult`
   - Else → treat as `{ ok: false, ... }` with stdout/stderr captured
3. Only show “No changes applied” when `ok: true` and `changed === false`.

✅ Verify:
- `npm run compile` has **no** TS errors about missing `.ok`
- Apply on a file that should change → summary indicates change + file updated
- Apply on a file that shouldn’t change → summary says no change, but still `ok: true`

---

### Step 6 — Add tests that prove the CLI args are correct
**Unit tests (pure TS, no VS Code host):**
1. Extract the arg-builder into a pure function:
```ts
export function buildEditEtlArgs(opts: { scriptPath: string; file: string; instruction: string; preserveIncludes: boolean; isJson: boolean; mode?: string }): string[] { ... }
```
2. Add tests asserting:
- args include `--file` followed by the exact file path
- args include `--instruction` followed by the full instruction string
- args include `--preserve-includes true`
- `--json` only included for JSON files

✅ Verify:
- `npm test` (pure unit tests) passes.

**VS Code extension-host tests (integration):**
1. Use `@vscode/test-electron` for any tests importing `vscode`.
2. Mock the Python runner so you can assert it was called with the args you expect.
   - Introduce a `PythonRunner` interface and inject it into the handler in tests.

✅ Verify:
- `npm run test:integration` (or your equivalent) runs under VS Code test host and passes.

---

### Step 7 — End-to-end manual verification
1. Open `test.json` (or a HOCON file) in VS Code
2. Run chat command:
   - `apply: add data_sourcing module reading parquet from ${source.srz.path}`
3. Confirm:
- No `argparse` missing-args error
- File is modified OR a valid “No changes applied” with a reason code
- `include "..."` lines remain unchanged

✅ Verify:
- The extension shows success summary and the file diff contains the intended change.

---

## Notes (do not skip)
- **Do not JSON.parse HOCON.** Always route HOCON edits through the Python tooling (`pyhocon`) and preserve `include`.
- Keep “pure logic” tests separate from VS Code host tests.

Now implement the changes, update tests, and report:
- Which files changed
- How to run the test suites
- A short summary of the fix

---

## If you need to inspect the Python CLI
Before finalizing arg names, open `src/python_modules/edit_etl_config.py` and confirm its argparse flags.
Use exactly those flag names in TS.
