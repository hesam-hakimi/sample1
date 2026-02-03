# Copilot Prompt — Phase 4 still says “No changes applied” even with `test.json` attached (Fix v2)

**Observed:** `@etl_copilot apply: add data_sourcing module reading parquet from ${source.srz.path}`  
Result: **“No changes applied”** (and file `test.json` does not change).

This means the **apply branch is triggered** (because it shows “Instruction received”), but the **apply pipeline returns a no-op**.

Your job: fix the extension so **either**:
- the file is actually edited, **or**
- the response contains a precise reason (`no_target`, `parse_error`, `filetype_not_allowed`, `no_changes`, `tool_error`) and does not pretend success.

Follow `Meta_Testing_Strategy_For_Copilot.md` (VS Code Extension Test Host).

---

## Step 1 — Make “No changes applied” impossible without a reason (instrument + reason codes)
1) Define a shared result type (export it from one place, e.g. `src/core/contracts.ts`):

```ts
export type ApplyResult = {
  ok: boolean;
  filePath?: string;
  summary: string[];
  reason?: "no_target" | "not_trusted" | "filetype_not_allowed" | "parse_error" | "tool_error" | "no_changes";
  details?: string;
};
```

2) In the apply command, **always** return an `ApplyResult` with:
- `ok=true` when text changes were written
- otherwise `ok=false` + `reason` + `details`

3) In chat, print:
- Target file
- Applied yes/no
- Reason + details when no

✅ Verify Step 1:
- Run the same apply prompt.
- If no edit happens, the message must show `reason` and `details` (not only “No changes applied”).

---

## Step 2 — Confirm you are editing the correct file (reference chip vs active editor)
In the chat handler:
1) Log the chosen target URI and how it was chosen:
- `"targetSource": "reference"` or `"activeEditor"`
2) If a file reference exists, prefer it.
3) Pass `targetUri` into the apply command (do NOT rely on active editor only).

✅ Verify Step 2:
- With NO editor open, attach `test.json` chip and run apply.
- Logs show `targetSource=reference` and `filePath` matches `test.json`.

---

## Step 3 — Fix the most common silent no-op: JSON parsing failures (JSON with comments / trailing commas)
If your apply implementation uses `JSON.parse`, it will fail on JSONC (comments, trailing commas) and you might be catching the error and returning no-op.

Implement robust parsing for `.json` using **jsonc-parser**:

- Add dependency: `jsonc-parser`
- Parse with `jsonc-parser.parse(text, errors, { allowTrailingComma: true })`
- If parse errors exist, return `reason="parse_error"` with a short message (first error).

✅ Verify Step 3:
- Put a trailing comma or comment into `test.json`
- Apply should not silently no-op. It must return `parse_error` OR still succeed if parser handles it.

---

## Step 4 — Implement a deterministic minimal edit (so apply definitely changes the file)
To prove the pipeline end-to-end, implement a minimum deterministic edit for JSON configs **without LLM**:

**Instruction:** “add data_sourcing module reading parquet from ${source.srz.path}”

Behavior for `.json`:
1) Parse config (jsonc-parser).
2) Ensure `root.modules` exists.
3) If `root.modules.data_sourcing` is missing, add:

```json
{
  "type": "file",
  "format": "parquet",
  "path": "${source.srz.path}",
  "loggable": true,
  "options": {}
}
```

4) If it exists, update/ensure `format="parquet"` and `path` matches the `${...}` token in the instruction.
5) Write the updated JSON back with stable formatting.

If config is `.conf`/`.hocon` and you don’t support it yet, return `tool_error` with a clear message.

✅ Verify Step 4:
- Start with `test.json`:
  ```json
  { "modules": {} }
  ```
- Run apply.
- File must now contain `"data_sourcing"`, `"format": "parquet"`, `"path": "${source.srz.path}"`.
- ApplyResult must have `ok=true`.

---

## Step 5 — Ensure the file write is actually committed
A very common bug: you compute `newText` but never write it (or you write to a doc that isn’t the same one on disk).

Use **one** consistent method:
- If editing open document: `TextEditor.edit(...)` then `document.save()`
- If file may not be open: `vscode.workspace.fs.readFile/writeFile`

Also log:
- oldText length
- newText length
- `oldText === newText` boolean
- write method used

✅ Verify Step 5:
- Logs show `oldText !== newText` and “writeFile succeeded” (or “editor edit applied + saved”).

---

## Step 6 — Add VS Code Extension Host integration tests (prove logic, prevent regression)

### Test A: applies data_sourcing to JSON
- Create temp `etl_test.json` with `{ "modules": {} }`
- Call the command with `targetUri` explicitly
- Assert:
  - result.ok === true
  - file content contains `"data_sourcing"` and `"parquet"`

### Test B: returns reason on parse_error
- Create json with invalid syntax (or simulate parse errors)
- Assert result.ok === false and reason === "parse_error"

### Test C: returns reason on no_target
- Call without targetUri and no active editor
- Assert reason === "no_target"

**TypeScript rule:** `executeCommand` must be typed:
```ts
const result = await vscode.commands.executeCommand<ApplyResult>(...)
```

✅ Verify Step 6:
- `npm test` passes in VS Code Extension Test Host.

---

## Final verification checklist
- Manual: Apply command changes `test.json` even if no active editor
- No more generic “No changes applied” without a reason
- `npm run compile` and `npm test` pass
