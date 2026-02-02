# Meta Prompt — Testing strategy for ETL VS Code extension (use this in ALL phases)

Use this as **global instruction** for GitHub Copilot when implementing any phase of the ETL extension work.

---

## 0) Hard rule: pick the correct test environment

### ✅ If a test imports or uses `vscode` APIs…
Examples:
- `vscode.commands.executeCommand(...)`
- `vscode.window.activeTextEditor`
- `vscode.workspace.applyEdit`
- `vscode.extensions.getExtension(...)`

➡️ **It MUST run inside the VS Code Extension Test Host** using `@vscode/test-electron`.
Do **NOT** run these tests with plain Node Mocha (`node mocha ...`) because `vscode` APIs won’t exist and you’ll get misleading failures.

### ✅ Plain Node/Mocha tests are allowed ONLY for “pure logic”
Examples:
- intent detection functions like `shouldApplyEdit(prompt)`
- JSON helpers
- string parsing / normalization
- small utilities that do NOT import `vscode`

---

## 1) Fix your repo test setup FIRST (once) — before writing any vscode-based tests

If the repo is currently running tests like:
```bash
node ./node_modules/mocha/bin/mocha --require ts-node/register src/test/**/*.test.ts
```
This is **plain Mocha**, not the Extension Test Host.

### Required VS Code extension test harness
Add (or reuse) the standard structure:

#### A) Install test harness dependency
```bash
npm i -D @vscode/test-electron
```

#### B) Add `src/test/runTest.ts`
This file launches VS Code and points it at your compiled test suite.

#### C) Add `src/test/suite/index.ts`
This file configures Mocha **inside** the VS Code test host and loads your `*.test.ts` files.

#### D) Update `package.json` scripts
Your test scripts must:
1) compile TypeScript
2) run the VS Code test host

Example:
```json
{
  "scripts": {
    "compile": "tsc -p ./",
    "test": "npm run compile && node ./out/test/runTest.js"
  }
}
```

> IMPORTANT: Tests that use `vscode` should live under `src/test/suite/**` and be compiled to `out/test/suite/**`.

### Verification for test harness (must pass before continuing any phase)
Run:
```bash
npm test
```
Expected:
- VS Code launches headlessly (test host)
- Mocha runs inside it
- A placeholder test passes

---

## 2) TypeScript rule: `executeCommand` returns `unknown` unless you type it

Your error `TS18046: 'result.filePath' is of type 'unknown'` happens because the command result is inferred as `unknown`.

### Correct pattern (preferred)
Always type the expected return:
```ts
type ApplyResult = { ok: boolean; summary: string[]; filePath: string };

const result = await vscode.commands.executeCommand<ApplyResult>(
  "etlCopilot.applyEtlEditToActiveFile",
  { instruction: "..." }
);

assert.ok(result);
assert.strictEqual(typeof result.filePath, "string");
```

### If your `executeCommand` typing doesn’t support generics
Use an explicit cast + runtime checks:
```ts
const result = (await vscode.commands.executeCommand("...")) as any;

assert.ok(result);
assert.strictEqual(typeof result.filePath, "string");
```

✅ In every test, do a runtime `typeof` check before calling `.endsWith()`.

---

## 3) Testing design: split tests into two buckets

### Bucket A — Pure unit tests (Node Mocha)
- No `vscode` import
- Run fast in CI
- Examples:
  - `shouldApplyEdit(...)`
  - prompt normalization
  - keyword maps
- Script suggestion:
```json
{ "test:unit": "mocha -r ts-node/register src/test-unit/**/*.test.ts" }
```

### Bucket B — Integration tests (VS Code Test Host)
- Uses `vscode` APIs
- Validates:
  - commands are registered
  - edits are applied to real documents
  - settings are honored (dryRun/autoSave)
- Script:
```json
{ "test": "npm run compile && node ./out/test/runTest.js" }
```

---

## 4) What to assert (avoid brittle UI tests)

### ✅ Prefer deterministic assertions
- file content changed / unchanged
- returned objects have expected shape
- command exists in `vscode.commands.getCommands(true)`
- document `isDirty` behavior (autoSave)

### ❌ Avoid asserting on UI message strings
Don’t rely on:
- `showInformationMessage` text content
- timing-based UI states

If you need UI signals:
- assert on returned result object
- log to OutputChannel but assert via a testable logger wrapper (injected dependency)

---

## 5) Each phase must include: tests + running tests

For **every phase** of the implementation:
1) Add/Update tests for that phase.
2) Run:
   - `npm test` (VS Code host tests)
   - plus `python -m pytest -q` if python changed
3) Only proceed if tests pass.

Copilot must **not** claim “tests pass” unless it actually runs them and shows a short result snippet.

---

## 6) Python testing rule (when a phase adds/changes python tools)
- Use `pytest`
- Use `subprocess.run` to test the CLI contract (stdin JSON → stdout JSON)
- Validate:
  - exit codes
  - stderr on failure
  - stdout JSON schema on success
- Script suggestion:
```json
{ "test:py": "python -m pytest -q" }
```

---

## 7) Minimal “Phase 1” test fix checklist (the issue you hit)
If a Phase 1 test reads:
```ts
assert(result.filePath.endsWith(".json"));
```
Fix it by:
- typing `executeCommand<ApplyResult>()`, and
- checking `result` exists and `typeof result.filePath === "string"` before `endsWith`.

---

## Copy/paste instruction for Copilot (short version)
- Any test that imports `vscode` must run via `@vscode/test-electron`, not plain Mocha.
- Set up `runTest.ts` + suite loader + `npm test` script before adding vscode tests.
- Always type `executeCommand<T>()` results (or cast + runtime checks).
- Keep pure logic tests separate from extension-host integration tests.
