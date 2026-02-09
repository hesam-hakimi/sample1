# Copilot Prompt — Fix apply() missing file, bad result schema, and VS Code not reflecting file updates

You are working in the **ETL Copilot VS Code extension**. The `apply:` workflow currently breaks in several ways:

## Symptoms to fix (all are real and must be addressed)
1. **If the user runs `apply:` without attaching/choosing a file**, the Python tool is invoked with missing args and fails:
   - `edit_etl_config.py: error: the following arguments are required: --file, --instruction`
2. **If the user passes an empty JSON `{}`**, the tool may partially update the file on disk, but VS Code does not reflect it (shows “content is newer” / needs reopen), and the extension throws:
   - `applyResult.summary.join is not a function`
3. Sometimes the file gets **corrupted** with non‑JSON text like repeated `Edit failed. Summary:` lines, and later errors show:
   - `JSON parse error: Expecting value: line 1 column 1 (char 0)`
   - `Error applying edit: Error: An object could not be cloned`
4. Validation step sometimes fails with:
   - `command 'etlCopilot.validateActiveEtlFile' not found`

Your job: **change the extension + python tool so apply is reliable, never corrupts files, and VS Code always shows the updated content immediately.**

---

## High-level design (required)
### A) The extension MUST NOT let the Python script write the target file directly
- The extension should read the file text and pass it to Python.
- Python should return a structured result (JSON) including `newText`.
- The extension should apply edits **through VS Code APIs** (`TextEditorEdit` / `WorkspaceEdit`) so the open editor updates instantly and we avoid “content is newer” conflicts.

### B) Standardize the tool result schema (no more `summary.join` failures)
Define a single TypeScript type used end-to-end:

```ts
export type ApplyEditResult = {
  ok: boolean;
  changed: boolean;
  file?: string;          // absolute path or uri.fsPath
  format: "json" | "hocon";
  newText?: string;       // present when ok=true
  summary: string[];      // ALWAYS array (even if single line)
  errors?: string[];      // optional
};
```

The extension must normalize any older shape defensively, but the goal is: **Python always returns this schema**.

---

## Implementation tasks (do all)

### 1) Fix target file resolution (no more missing `--file` / `--instruction`)
In `applyEditHandler.ts` (or equivalent), implement `resolveTargetUri(...)`:

**Rules**
- If request includes a file reference/context → use it.
- Else, use `vscode.window.activeTextEditor?.document.uri`.
- Else: **do not call Python**; return a friendly message: “Open an ETL JSON/HOCON file (or attach it) then run apply again.”

Also:
- If the resolved document is `untitled:` or not saved → ask user to save first.

### 2) Pass file contents to Python via stdin (no disk writes)
Update Node/TS side:
- Call `python .../edit_etl_config.py --mode apply --format <json|hocon> --instruction "<...>" --stdin`
- Send the current file text to stdin.
- Capture **stdout** and **stderr** separately.
- Treat **stdout** as **machine JSON only**. Any logs must be in stderr.

If Python exits non-zero:
- Show stderr in the chat response.
- **Do not modify the file.**

If Python exits zero but stdout is not valid JSON:
- Show a clear error in chat including a short excerpt of stdout/stderr.
- **Do not modify the file.**
- Add tests for this case.

### 3) Update `edit_etl_config.py` to support stdin + return structured JSON
Modify `src/python_modules/edit_etl_config.py`:

- Add flag `--stdin` (boolean). When present, read the full config text from stdin instead of `--file`.
- Keep `--file` supported for CLI/manual use, but the extension will use `--stdin`.
- Determine format:
  - If `--format json`: parse JSON; if empty or `{}` and instruction needs modules, create `modules` object.
  - If `--format hocon`: parse with pyhocon; preserve substitutions like `${...}`; preserve `include` statements (details below).
- Output ONLY the `ApplyEditResult` JSON to stdout (no extra prints).
- Send debug/info logs to stderr if needed.
- On failure: output `{"ok": false, "changed": false, "format": "...", "summary": [...], "errors": [...]}` to stdout and exit non-zero (or exit 0 but ok=false; choose one approach and make TS handle it consistently).

**Important include handling (HOCON)**
- `include "..."` lines are *not JSON* and are semantically important.
- Preserve them by:
  1) Extracting include lines (and their original relative order) before parsing.
  2) Parse/modify the rest using pyhocon.
  3) Render back to HOCON.
  4) Re-insert the include lines near the top exactly once (avoid duplicates).
- Add a unit test fixture HOCON containing include lines.

### 4) Apply edits through VS Code so the open editor updates immediately
In TypeScript:
- If `result.ok && result.newText`:
  - Open the document (or use active editor doc if same URI).
  - Apply a single full-range replacement using `WorkspaceEdit` or `TextEditorEdit`.
  - After applying, if command is `apply`, call `await document.save()` (or make this configurable).
- This prevents:
  - “content is newer”
  - having to close/reopen to see changes
  - file corruption due to external writes

### 5) Fix `applyResult.summary.join is not a function` forever
- Ensure `ApplyEditResult.summary` is always an array.
- Add a small helper:

```ts
function normalizeSummary(summary: unknown): string[] {
  if (Array.isArray(summary)) return summary.map(String);
  if (typeof summary === "string") return summary ? [summary] : [];
  if (summary == null) return [];
  return [String(summary)];
}
```

Use it before rendering to chat, even if Python is updated.

### 6) Fix “An object could not be cloned”
This commonly happens when passing non-serializable objects into places that require cloning.

- Do **not** store VS Code objects (Uri, Range, TextDocument, etc.) inside objects that get posted/cloned.
- If you send any data to webviews or telemetry or serialize results, only send primitives/POJOs.
- Ensure the returned `ApplyEditResult` you log/emit contains only JSON-safe values.

Add a regression test that ensures your result object is JSON-serializable:
- `JSON.stringify(result)` must not throw.

### 7) Fix `etlCopilot.validateActiveEtlFile not found`
Do one of these (preferred: #1):
1. **Remove** the executeCommand call and run validation directly (call a local function).
2. OR register the command properly:
   - `package.json` contributes.commands includes `etlCopilot.validateActiveEtlFile`
   - `activationEvents` includes `onCommand:etlCopilot.validateActiveEtlFile`
   - `activate()` registers it via `vscode.commands.registerCommand(...)`

Also: if validation is optional, guard it:
- check `await vscode.commands.getCommands(true)` contains it before calling.

---

## Tests (must add)
### TypeScript (Jest)
- `resolveTargetUri`:
  - returns active editor uri when no file passed
  - throws/returns user-friendly error when nothing is open
- `normalizeSummary` handles: array, string, null, object
- handler behavior when python stdout is invalid JSON:
  - asserts **no file edits** performed

### Python (pytest)
- JSON `{}` + instruction “add data_sourcing module reading parquet...” should:
  - return ok=true
  - changed=true
  - include `modules.data_sourcing_read_parquet` (or your decided name)
- HOCON fixture with include line:
  - output preserves include line
  - modifications applied without duplicating include
- Empty input should return ok=false with helpful errors and changed=false

---

## Acceptance criteria
- Running `apply:` with no file open/attached does **not** call python; returns a clear message.
- Running `apply:` on `{}` produces a valid updated JSON file **visible immediately in VS Code** (no reopen, no “content newer”).
- The extension never writes `Edit failed...` text into config files.
- `applyResult.summary.join` never throws.
- No “An object could not be cloned” errors.
- Validation step does not fail due to missing command.

---

## Notes for the change
- Prefer minimal invasive refactor: introduce `runPythonEditTool(inputText, instruction, format)` and reuse it.
- Keep backward compatibility where possible, but prioritize correctness and not corrupting files.
