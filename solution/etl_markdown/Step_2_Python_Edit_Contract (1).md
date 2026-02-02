# Step 2 — Implement Python contract: edit ETL config in-memory + pytest unit tests

## Goal
Create a Python entrypoint that:
- Receives: **instruction + file type + current file content**
- Returns: **updated content + summary** (as JSON on stdout)
- Emits errors to stderr with non-zero exit code

This lets TypeScript apply edits safely without relying on Webviews.

---

## Create a new Python script
Create: `src/python_modules/edit_etl_config.py`

### Inputs
Prefer **stdin JSON** to avoid command-line length issues:
```json
{
  "instruction": "Add data_sourcing module ...",
  "fileType": "json",
  "content": "{... current file ...}"
}
```

### Output (stdout JSON)
On success:
```json
{
  "ok": true,
  "updatedText": "....",
  "summary": ["Added data_sourcing module", "Updated writer.path"]
}
```

On failure:
- exit code: non-zero
- stderr: error message (optionally JSON)

---

## Implementation guidance
### JSON configs
- Parse JSON
- Apply changes
- Dump pretty JSON (stable formatting)

### HOCON configs
- Use a real parser (e.g., `pyhocon`) if available in the environment.
- Keep V1 simple:
  - Either: support insert/update for known module keys only
  - Or: if parser not installed, return a clear error (do not attempt regex edits)

## Safety requirements
- Never execute arbitrary code from the instruction.
- Only perform config transforms.
- Do not write to disk (in-memory transformation only).

---

## Unit tests for Step 2 (pytest)

### Add test dependencies
If pytest isn’t already available:
- Add it to your python env requirements (project standard), or
- Add a `requirements-dev.txt` containing `pytest`

### Create tests
Create: `tests/test_edit_etl_config.py` (or `src/python_modules/tests/...` depending on your repo layout)

**Minimum test cases:**

1. **Valid JSON input returns ok + updatedText**
   - content: `{ "modules": {} }`
   - instruction: “add module data_sourcing …”
   - assert:
     - stdout parses to JSON
     - `ok == true`
     - `updatedText` is valid JSON
     - `summary` is a non-empty list

2. **Invalid JSON content fails safely**
   - content: `{ this is not json }`
   - assert:
     - process return code != 0
     - stderr contains a clear message
     - stdout is empty or not misleading

3. **HOCON path behavior (choose one)**
   - If you support HOCON in V1:
     - assert `updatedText` is non-empty and includes expected keys
   - If you don’t support HOCON in V1:
     - assert it fails with a clear “HOCON parser missing / not supported” error

4. **No disk writes**
   - Ensure the script does not create/modify files in the working directory.
   - Example: record directory listing before/after and assert no new files.

### Test execution helper
In pytest, call the script using `subprocess.run`, feed stdin JSON, capture stdout/stderr.

---

## Verification (must pass before Step 3)

### Run python unit tests
From repo root:
```bash
python -m pytest -q
```

### Expected results
- All pytest tests pass
- Script returns valid JSON contract on success
- Errors are signaled via exit code + stderr
