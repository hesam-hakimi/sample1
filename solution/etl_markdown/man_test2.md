## Fix upload failure: InvalidDocumentKey (sanitize `id` before upload)

### Error
`InvalidDocumentKey: Keys can only contain letters, digits, underscore (_), dash (-), or equal sign (=)`
Current ids include `.` like:
`field.aczrrdw.v_dlv_dep_agmt_clr_base_table.HOLD_AMT`

### What to change
In `scripts/search_upload_metadata.py`, add a deterministic key-sanitization step and apply it to EVERY document BEFORE upload.

### Requirements (must follow exactly)
1) Create a helper function:
- `sanitize_search_key(raw_id: str) -> str`

2) Sanitization rules:
- Allowed characters: `[A-Za-z0-9_\-=]`
- Replace ANY other character (including `.`) with `_`
- To prevent collisions, append a stable suffix derived from the original raw id:
  - Use SHA1 (or similar) of `raw_id`
  - Take first 10 hex chars
  - Final format: `<sanitized_base>__<hash10>`
- If sanitized_base becomes very long, truncate it so the final key stays reasonable (keep at least 50 chars + suffix).

3) Apply sanitization:
- For every loaded doc:
  - Store original value in a local variable: `raw_id = doc["id"]`
  - Set: `doc["id"] = sanitize_search_key(raw_id)`
  - If `raw_id != doc["id"]`, append to `doc["content"]` a line:
    - `RAW_ID: <raw_id>`
  (Do NOT add new fields to the document schema; only modify `id` and `content`.)

4) Add logging:
- Print per-index:
  - total docs loaded
  - how many ids were sanitized (raw != new)
  - sample mapping for first 3 sanitized docs: `raw_id -> new_id`

5) Re-run upload:
- Keep using `merge_or_upload_documents` in batches.
- Do NOT recreate indexes.

### After patch
Run:
- `python scripts/search_upload_metadata.py`

### Output needed
Paste the console output (especially:
- sanitized counts + sample mappings
- upload summary per index
- validation search results)
