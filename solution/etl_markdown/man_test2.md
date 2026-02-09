You are working in THIS repo. Create a minimal Python project for a Gradio + Azure OpenAI (MSI) + SQL Server (pyodbc) app.

Constraints:
- Do NOT use OpenAI Runner/Agent/Agents SDK.
- Use openai.AzureOpenAI client (chat.completions.create) with azure_ad_token_provider from ManagedIdentityCredential.
- Keep dependencies minimal and explicit.
- Add pytest tests.

Create these files:
1) requirements.txt with:
   - gradio
   - openai
   - azure-identity
   - pyodbc
   - pandas
   - pytest
   - python-dotenv (optional but nice)
2) .env.example with placeholders:
   AZURE_OPENAI_ENDPOINT=
   AZURE_OPENAI_API_VERSION=2024-10-21
   AZURE_OPENAI_DEPLOYMENT=gpt-4.1
   SQL_SERVER=
   SQL_DATABASE=
   SQL_DRIVER=ODBC Driver 18 for SQL Server
3) app/__init__.py
4) app/config.py:
   - reads env vars (use dotenv if present)
   - validates required settings with clear error messages
5) tests/test_config.py:
   - tests missing env vars raise a helpful exception

Acceptance criteria:
- `pytest -q` runs locally and passes (tests should not require real Azure/SQL connections).
- Config validation errors are clear and actionable.
