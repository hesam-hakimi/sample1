## Step: Validate the “0 rows fallback” end-to-end (CLI)

### 0) Prep (do this once)
From the repo root (same folder where `app/` exists):

1) Confirm you are using the venv python:
- Linux/mac:
  - `which python`
  - `python -V`
- If `python` is not your venv, use the explicit path you used before:
  - `/app1/tag5916/projects/text2sql_v2/.venv/bin/python -V`

2) Turn on debug (so we can see diagnostics)
Set:
- `DEBUG=true`
(keep other .env values as-is)

---

### 1) Run the “0 rows” scenario
Run exactly:

- `python -m app.main_cli "show me the list of all clients who are based in usa"`

If `python` is not found or wrong interpreter, run:
- `/app1/tag5916/projects/text2sql_v2/.venv/bin/python -m app.main_cli "show me the list of all clients who are based in usa"`

---

### 2) What to paste back to me
Paste ALL of the CLI output, including:
- The generated SQL
- The “0 rows fallback” diagnostic section (top values, suggested alternatives)
- Any stack trace (if it crashes)

---

### 3) Quick pass/fail criteria (you can eyeball)
✅ Pass if:
- The command does NOT crash
- It detects 0 rows
- It prints diagnostics and a suggestion / question for the user

❌ Fail if:
- It crashes
- It loops/retries endlessly
- Diagnostics are empty or irrelevant (e.g., no mention of TERR_CD / country-like columns)

---

### 4) If it still returns 0 rows with no useful suggestion
Run this extra command and paste output too:
- `python -m app.main_cli "what are the top 20 values for TERR_CD in v_dlv_dep_prty_clr"`

(If your app doesn’t support that question, just paste whatever it prints.)
