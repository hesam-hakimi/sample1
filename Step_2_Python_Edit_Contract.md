# Step 2 — Implement Python contract: edit ETL config in-memory and return updated content

## Goal
Create a Python entrypoint that:
- Receives: **instruction + file type + current file content**
- Returns: **updated content + summary** (as JSON on stdout)
- Emits errors to stderr with non-zero exit code

This lets TypeScript apply edits safely without relying on Webviews.

## Create a new Python script
Create: `src/python_modules/edit_etl_config.py`

### Inputs
Choose one of these approaches:
- **Args**: pass `instruction`, `file_type`, and `content` (careful with shell limits), OR
- **stdin JSON** (recommended): pass one JSON payload via stdin to avoid arg length issues.

Recommended input (stdin JSON):
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
- Validate that output is syntactically correct JSON/HOCON (as best as possible).

## Verification (must pass before Step 3)
### CLI test
1. Create a tiny JSON sample:
```json
{ "modules": {} }
```
2. Run:
- If using stdin JSON:
  - `echo '{...}' | python edit_etl_config.py`
- If using args:
  - `python edit_etl_config.py --file_type json --instruction "..." --content "{...}"`

3. Confirm stdout:
- Is valid JSON
- Contains `ok: true` and `updatedText`

### Error test
1. Pass invalid JSON content.
2. Confirm:
- Non-zero exit code
- stderr has a clear error message
- No partial output written to files (in-memory only)
