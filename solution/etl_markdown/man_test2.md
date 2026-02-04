# Copilot Prompt — Fix “JSON parse error / No changes applied” when applying ETL edits (HOCON + JSON)

Paste this into **GitHub Copilot Chat** in the ETL extension repo.

---

You are working in a VS Code extension (“ETL Copilot”) that edits ETL config files using a Python helper script `src/python_modules/edit_etl_config.py`.
Right now, when I run:

`@etl_copilot apply: add data_sourcing module reading parquet from ${source.srz.path}`

I hit these issues in order:

1) **JSON parse error** (Python):  
`[edit_etl_config.py] JSON parse error: Expecting value: line 2 column 1 (char 1)`  
This happens when the file is **HOCON-like** (e.g., has `include "..."`, unquoted keys, comments, trailing commas) but the extension treats it as JSON (often because of `.json` extension or `--json` flag).

2) After some fixes, the command runs but still returns:  
`No changes; type=json; file=...`  
Meaning: parsing succeeded, but **the instruction didn’t map to a deterministic edit**, so no update was applied.

## Goal
Make the apply flow **format-aware**, **diagnostic**, and **deterministic**:

- Support both **strict JSON** and **HOCON** (including `include` lines and `${var}` substitutions).
- If the file looks like HOCON (even if it’s named `.json`), do **NOT** force JSON parsing.
- Always return a structured result with:
  - `ok: boolean`
  - `changed: boolean`
  - `format: "json" | "hocon"`
  - `reasonCode` (e.g., `PARSE_ERROR`, `NO_OP_UNMAPPED_INSTRUCTION`, `NO_ACTIVE_FILE`, `APPLIED`)
  - `details` (stderr, parse exception, etc.)
- Implement a deterministic edit for the instruction:
  - “add data_sourcing module reading parquet from ${source.srz.path}”
  - It must **add** a module block under the existing `modules` section (create `modules` if missing), using the repo’s existing schema.

---

# Step 1 — Reproduce and add failing tests (before fixing)

## 1.1 Add fixtures
Search the repo for existing ETL config examples (JSON + HOCON). If none exist, create minimal fixtures under:
- `tests/fixtures/config-json.json` (strict JSON)
- `tests/fixtures/config-hocon.conf` (HOCON with an `include` line + modules block)

**HOCON fixture must include** an `include "..."` line to verify preservation.

## 1.2 Add Python-focused tests (no VS Code APIs)
Create tests that run the python tool as a subprocess (or call a factored pure function).  
Location suggestion: `src/python_modules/tests/test_edit_etl_config.py` (pytest)

Add tests:

- `test_apply_add_parquet_module_json()`  
  - Input: `config-json.json`
  - Run: `python edit_etl_config.py --file <path> --instruction "<instruction>" --mode apply --preserve-includes true --json`
  - Assert: output file now contains the new module under `modules` and it is valid JSON.

- `test_apply_add_parquet_module_hocon_preserves_include()`  
  - Input: `config-hocon.conf`
  - Run: same command **without** `--json`
  - Assert:
    - include line still exists exactly once at top (or original position)
    - new module exists under `modules`
    - file remains HOCON-like (not converted to JSON)

## 1.3 Add TS unit tests for “format detection”
Create `src/test/unit/detectConfigFormat.test.ts` with pure unit tests (NO `vscode` import).  
Tests should cover:
- strict JSON detection
- HOCON detection via:
  - presence of `include`
  - unquoted keys with `:`
  - `modules: { ... }`
  - trailing commas / comments
- fallback behavior: `.json` extension but HOCON content => returns `hocon`

✅ **Verify Step 1**: `npm run compile` passes, `pytest` and `npm test` show failing tests that match the current bug.

---

# Step 2 — Fix format detection + CLI flag routing (TS)

## 2.1 Implement `detectConfigFormat(text, uri)`
Add a pure helper under `src/core/detectConfigFormat.ts`:
- Try `JSON.parse(text)` safely; if success => `json`
- If fail, or if text matches HOCON patterns (`^\s*include\s+["']`, unquoted keys with `:` and `{`, etc.) => `hocon`
- Don’t rely solely on extension `.json` / `.conf`; content wins.

## 2.2 Ensure `applyEditHandler` routes flags correctly
In `applyEditHandler.ts` (or wherever Python is invoked):
- Read file content first.
- Determine `format = detectConfigFormat(text, uri)`.
- Build python args:
  - always include: `--file`, `--instruction`, `--mode apply`, `--preserve-includes true`
  - include `--json` **only when format === "json"**
- Ensure paths and instruction are passed as **separate argv elements** (no manual quoting inside one string).

## 2.3 Capture stderr/stdout cleanly
Update the Node child-process call:
- Capture `stdout` and `stderr`
- If exit code non-zero:
  - return structured error with stderr included (trimmed)
- If zero:
  - parse the python output (prefer JSON output from python tool; see Step 3)

✅ **Verify Step 2**:
- Unit tests for `detectConfigFormat` pass.
- Running the apply command no longer forces JSON parsing on HOCON input.

---

# Step 3 — Make Python tool return structured JSON + robust parsing

## 3.1 Refactor python into pure functions
In `edit_etl_config.py`:
- `read_text(file_path) -> str`
- `parse_config(text, format) -> (config_obj, includes_meta)`
- `apply_instruction(config_obj, instruction) -> (new_config_obj, changed, details)`
- `render_config(new_config_obj, format, includes_meta) -> str`
- `write_text(file_path, text)`

## 3.2 Implement tolerant HOCON parsing + include preservation
- If format is `hocon`:
  - Extract and preserve `include` lines (store raw lines + original positions if possible).
  - Parse the remaining config via `pyhocon.ConfigFactory.parse_string(...)`.
- If format is `json`:
  - Use `json.loads` (strict).
- If JSON parsing fails but HOCON parse succeeds: return `format="hocon"` and proceed (this supports “.json containing HOCON”).

## 3.3 Output a JSON result every time
Print one JSON line to stdout at the end:
```json
{
  "ok": true,
  "changed": true,
  "format": "hocon",
  "reasonCode": "APPLIED",
  "summary": "...",
  "details": { "addedModuleKey": "..." }
}
```
On error:
```json
{
  "ok": false,
  "changed": false,
  "reasonCode": "PARSE_ERROR",
  "format": "json",
  "error": "…",
  "stderr": "…"
}
```

✅ **Verify Step 3**:
- `pytest` passes for both JSON and HOCON fixtures.
- Manual run:
  - `python src/python_modules/edit_etl_config.py --help`
  - run on fixtures and confirm JSON output + file updated

---

# Step 4 — Make the edit deterministic for this instruction (avoid “No changes”)

## 4.1 Discover the real module schema
Search for how modules are represented in existing configs and/or how the ETL engine reads them.
Find:
- key names used (`type`, `module`, `options`, etc.)
- examples of `data_sourcing` or parquet read patterns

Do NOT invent a schema; use what the repo already uses.

## 4.2 Implement a rule-based handler
Add a handler in python (or TS if edits happen there) that matches:
- contains `data_sourcing`
- contains `parquet`
- contains `from` and captures the path token (e.g., `${source.srz.path}`)

Then:
- Ensure `modules` exists
- Add a new module entry with a stable key, e.g.:
  - `data_sourcing_read_parquet` (or consistent with repo conventions)
- If the key already exists, either:
  - update its `path` option, or
  - create a unique suffix `_2`, `_3`, etc.

Return `changed=True` only if the config text actually changed.

## 4.3 Improve “No changes” messaging
If instruction matches but doesn’t cause a diff (module already present), return:
- `ok: true`
- `changed: false`
- `reasonCode: "NO_OP_ALREADY_PRESENT"`
- include a summary explaining why.

If instruction doesn’t match any handler:
- `ok: true`
- `changed: false`
- `reasonCode: "NO_OP_UNMAPPED_INSTRUCTION"`
- summary: “Instruction not recognized. Supported patterns: …”

✅ **Verify Step 4**:
- Add tests asserting:
  - module is added on first run
  - second run returns NO_OP_ALREADY_PRESENT
  - unmapped instruction returns NO_OP_UNMAPPED_INSTRUCTION with helpful summary

---

# Step 5 — Extension-host integration tests (VS Code)

## 5.1 Use VS Code test harness (NOT plain mocha)
If any test imports `vscode`, run via `@vscode/test-electron` in the extension host.

Add/confirm:
- `src/test/runTest.ts` harness
- `npm test` runs extension-host tests

## 5.2 Integration test for apply command
Create an extension-host test that:
- opens a fixture file in an editor
- runs the command: `etl-copilot.applyEditToActiveFile` (use actual command id)
- verifies file text now contains the added module
- verifies include preserved for HOCON fixture

✅ **Verify Step 5**: `npm test` passes in CI and locally.

---

# Output expectations
When I run the apply prompt against a HOCON-like config, I should see:
- A success message including:
  - `format=hocon`
  - `changed=true`
  - module key added
- The file should actually be updated on disk.

When I run it against JSON:
- It should stay JSON and update the `modules` object correctly.

---

# Constraints
- Do not change the external command ids or user-facing command names.
- Keep backward compatibility: existing apply flows must keep working.
- Keep pure logic testable without `vscode`.
- Keep `vscode`-dependent tests only in extension-host harness.

Start with Step 1 and proceed step-by-step. After each step, show:
- files changed
- commands I should run to verify
- expected output
