## Fix Step 5 — OpenAI SDK mismatch (KEEP openai>=1.0)

### What happened
Runtime error indicates the code is calling `openai.ChatCompletion` (old SDK),
but our environment has `openai>=1.0` (new SDK). We should NOT downgrade.

### Required decision
- Keep `openai>=1.0` in requirements
- Update code to use `AzureOpenAI` client

### Tasks
1) Search the repo for old usage:
   - `grep -R "ChatCompletion" -n app scripts`
   - `grep -R "openai\\." -n app scripts`
   - `grep -R "import openai" -n app scripts`

2) Update **LLM client** implementation (likely `app/core/llm_service.py`):
   - Use:
     - `from openai import AzureOpenAI`
     - `from azure.identity import ManagedIdentityCredential, DefaultAzureCredential, get_bearer_token_provider`

   - Create the client like this (match our existing auth pattern):
     - credential: `ManagedIdentityCredential(client_id=AZURE_CLIENT_ID)` if AZURE_CLIENT_ID exists, else `DefaultAzureCredential()`
     - token provider scope: `"https://cognitiveservices.azure.com/.default"`
     - `client = AzureOpenAI(azure_endpoint=AZURE_OPENAI_ENDPOINT, api_version=AZURE_OPENAI_API_VERSION, azure_ad_token_provider=token_provider)`

   - Replace old call with:
     - `client.chat.completions.create(model=AZURE_OPENAI_DEPLOYMENT, messages=[...], temperature=0, ...)`

3) Ensure response parsing uses:
   - `resp.choices[0].message.content`

4) Make NO other behavioral changes.
   - Keep existing prompt structure
   - Keep retry logic, logging, debug mode unchanged

### Validation
After patch, rerun:
- `python -m app.main_cli "show me the list of all clients who are based in usa"`

Paste the full console output or stack trace.
