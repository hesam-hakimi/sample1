# Copilot Implementation Prompt — Add HOCON-aware editing (preserve `include`) + reliable tests

> **Use this prompt in GitHub Copilot Chat inside the repo.**  
> Goal: make the ETL VS Code extension correctly edit real ETL config files that are **HOCON/Typesafe Config** (often with `include` lines), without fragile `JSON.parse` behavior, and add a test strategy that prevents regressions.

---

## 0) Ground rules (must follow)

1. **Do NOT parse HOCON files using `JSON.parse`.** If the file contains `include` or HOCON syntax, treat it as HOCON.
2. **Never delete or rewrite `include ...` lines unintentionally.** Preserve them exactly (or preserve the full header block) when writing changes back.
3. **No silent no-ops.** If “No changes applied”, the extension must output a **reason code** (e.g., `no_target`, `parse_error`, `no_changes`, `tool_error`, `unsupported_file`) and enough diagnostics to debug.
4. **Testing:** any test that imports `vscode` must run in **VS Code Extension Test Host** (`@vscode/test-electron`), not plain Mocha.
5. Keep changes backward compatible: existing JSON editing paths must continue working.

---

## 1) Understand current code (no edits yet)

**Task**
- Locate where the “apply” command is implemented (e.g., `etlAssistantHandler.ts`, `extension.ts`, or command registration).
- Find the function that:
  - resolves the target file (active editor vs reference)
  - reads file text
  - attempts to parse/update it (likely uses `JSON.parse` or “jsonc-parser”)
  - writes updates and returns “No changes applied” summary

**Verification**
- Paste in chat the file paths + function names you found and a short summary of the current flow (5–10 lines).

---

## 2) Add config type detection (JSON vs HOCON)

**Task**
Create a small module (new file) e.g. `src/core/configType.ts`:
- Export `detectConfigType(text: string, filePath?: string): 'json' | 'jsonc' | 'hocon' | 'unknown'`
- Heuristics (minimum):
  - If text contains `\ninclude ` or starts with `include ` → `hocon`
  - If it contains `modules {` or `modules:` with unquoted keys, or `${var}` substitutions → `hocon`
  - If it starts with `{` or `[` and parses as JSON → `json`
  - If it has comments (`//` or `/* */`) but otherwise JSON-ish → `jsonc`
- Export `isHoconLike(text: string): boolean` (used by the handler)

**Verification**
- Add unit tests (pure TS, no `vscode`) under `src/test/unit/configType.test.ts`:
  - detects HOCON when `include "../x.yaml"` exists
  - detects HOCON when `${source.srz.path}` exists
  - detects JSON for valid JSON
  - detects JSONC when comments exist
- Run:
  - `npm run compile`
  - `npm test` (unit tests only; no `vscode` imports)

---

## 3) Standardize result types (fix TypeScript “property ok doesn’t exist” errors)

**Task**
Define a **single discriminated union** type for apply outcomes (new file `src/core/applyResult.ts`):

```ts
export type ApplyResult =
  | { ok: true; changed: boolean; reason: 'applied' | 'no_changes'; summary: string; filePath: string; newText: string }
  | { ok: false; reason: 'no_target' | 'unsupported_file' | 'parse_error' | 'tool_error'; summary: string; filePath?: string; error?: string };
export function isOk(r: ApplyResult): r is Extract<ApplyResult, { ok: true }> { return r.ok; }
```

Then update existing code to use this type everywhere instead of `any` / `unknown` results.
- Replace checks like `applyResult && applyResult.ok` with `isOk(applyResult)` or optional chaining if needed.
- Make “changed” determination explicit: `changed === true` only when `newText` differs and a write occurred.

**Verification**
- `npm run compile` must be clean (no TS errors).
- Unit test: construct both variants and ensure type guard works.

---

## 4) Route HOCON edits through Python (do NOT re-implement parsing in TS)

You already have Python utilities under `src/python_modules/` (examples in repo: `edit_etl_config.py`, `hocon_converter.py`, `write_module.py`, `utils.py`).

**Task**
Create `src/core/pythonBridge.ts` that runs python scripts reliably:
- Use `child_process.execFile` with `python` (or configurable python path)
- Pass arguments safely (no shell string concatenation)
- Capture stdout/stderr
- Return a structured result or an `ApplyResult` error

**Define a single Python entrypoint for apply**
- Use existing `src/python_modules/edit_etl_config.py` (or adjust it) so it supports:
  - input: `--file <path> --instruction <text> --mode apply --preserve-includes true`
  - output: **JSON to stdout**:
    ```json
    { "ok": true, "changed": true, "reason": "applied", "summary": "...", "newText": "..." }
    ```
    or
    ```json
    { "ok": false, "reason": "parse_error", "summary": "...", "error": "..." }
    ```
- If the Python script currently prints plain text, update it to print JSON only (or add a `--json` flag).

**TS handler behavior**
- When `detectConfigType(...) === 'hocon'`, call Python apply.
- When JSON/JSONC, keep existing logic (or use `jsonc-parser` for JSONC).
- Always include in the summary:
  - detected type
  - target filePath
  - reason code
  - whether it changed
  - if no change, *why*

**Verification**
- Add a fixture HOCON file under `src/test/fixtures/sample_with_include.conf` containing:
  - an `include "../sql/ctr_work_dates_enrich.yaml"` line
  - a `modules { ... }` or `modules: { ... }` block
- Add a **pure TS unit test** that calls the Python script directly via `pythonBridge` (NO `vscode` imports) and asserts:
  - returned JSON has `{ ok: true }`
  - `newText` still contains the original include line
  - `newText` contains the new/updated module requested
- Run:
  - `npm run compile`
  - `npm test`

> If python isn’t available in CI, make the python-based test conditional or document it. But keep at least one local verification step.

---

## 5) Fix “No changes applied” by surfacing root causes

**Task**
Update the apply flow to never output “No changes applied” without including:
- the reason code
- file path used
- detected config type
- whether parsing succeeded
- whether write succeeded
- old/new length (or hash) when safe

Additionally:
- If no active editor and no reference file: return `{ ok:false, reason:'no_target' }` and show a friendly message.
- If file is HOCON but Python fails: return `{ ok:false, reason:'tool_error' }` with stderr in logs (not necessarily in UI).
- If parse fails: `parse_error` and show the first line of error (not huge stack traces in UI).

**Verification**
- Add unit tests for:
  - no target file → reason `no_target`
  - unsupported extension → reason `unsupported_file`
  - parse error on malformed JSON → reason `parse_error`
- Confirm the UI message shows reason codes.

---

## 6) Add VS Code Extension Host integration tests (for commands)

Your earlier failures happened because `vscode` APIs don’t run in plain Mocha.

**Task**
Set up extension tests using `@vscode/test-electron`:
- Add `src/test/runTest.ts` (standard harness) and `src/test/suite/index.ts`
- Update `package.json` scripts:
  - `test:unit` → pure mocha tests that do NOT import vscode
  - `test:ext` → runs VS Code extension host tests via `node ./out/test/runTest.js`
  - `test` → runs both in order: `npm run test:unit && npm run test:ext`

Create an integration test `src/test/suite/applyCommand.hocon.test.ts`:
- Open the fixture file in VS Code test workspace
- Programmatically set it as active editor
- Execute the command the extension registers (e.g., `vscode.commands.executeCommand('etlCoding.applyEtlEditToActiveFile', ...)` or your actual command id)
- Verify the file content changed and still contains the `include` line

**Verification**
- Run locally:
  - `npm run compile`
  - `npm run test:unit`
  - `npm run test:ext`
  - `npm test`

---

## 7) Acceptance criteria (must be true before finishing)

1. For a HOCON file containing `include`, the extension can apply “add data_sourcing module reading parquet from ${source.srz.path}” and **actually modifies the file**.
2. The `include` line remains present and unchanged.
3. If the file cannot be edited, the user sees a reason code (not only “No changes applied”).
4. Unit tests cover detection + result typing.
5. Extension tests run in VS Code host and validate the command is registered and edits correctly.
6. `npm run compile` passes with zero TS errors.

---

## 8) Implementation note for the specific feature you’re testing

When the user asks:

`apply: add data_sourcing module reading parquet from ${source.srz.path}`

The Python apply should ensure `modules.data_sourcing` exists (or add it) with keys equivalent to:

- `type: "file"`
- `format: "parquet"`
- `path: ${source.srz.path}`
- `loggable: true`
- optional `options { ... }` only if required by your framework

**Do not invent framework-specific keys**; use patterns from existing ETL configs in the repo if present.

---

### End of prompt
