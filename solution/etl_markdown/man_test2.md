We have a bug: AI Search connection test fails with:
"Failed to connect to Azure AI Search: Parameter 'endpoint' must not be None."

Root cause:
os.getenv("AI_SEARCH_ENDPOINT") is returning None because the .env file is not being loaded into the Python process.

Implement a robust, consistent env/config loader so .env ALWAYS loads when running the app and tests.

Requirements:
1) Add python-dotenv as a dependency (requirements.txt) and load it exactly once at startup.
   - Add: python-dotenv
2) In app/config.py:
   - import dotenv and call load_dotenv() at module import time OR in Config.__init__ before reading env vars.
   - Then read all env vars via os.getenv.
   - Validate:
      - AI_SEARCH_ENDPOINT must be non-empty when AI Search metadata store is enabled
      - AI_SEARCH_INDEX must be non-empty
   - Strip quotes if present (support values like AI_SEARCH_ENDPOINT="https://...").
   - Raise ValueError with clear message listing missing vars.

3) Ensure the app entrypoint calls config early.
   - In main.py/app.main, instantiate Config() at startup.
   - This guarantees load_dotenv was applied.

4) Update app/metadata_store.py:
   - Do NOT use os.getenv directly inside test_ai_search_connection.
   - Accept endpoint/index/use_msi as explicit parameters OR read from Config passed in.
   - Provide a helper:
       def test_ai_search_connection(endpoint: str, index: str, use_msi: bool) -> tuple[bool,str]
     and it must fail fast if endpoint/index empty with a friendly message.

5) Add a small CLI helper script scripts/print_env.py (for debugging):
   - prints whether AI_SEARCH_ENDPOINT and AI_SEARCH_INDEX exist and show their first 30 chars only.

6) Tests:
   - tests/test_config_env_loading.py:
     - create a temp .env with AI_SEARCH_ENDPOINT and AI_SEARCH_INDEX
     - ensure Config() loads it and endpoint is not None
   - Ensure tests do not require real Azure.

Acceptance criteria:
- Running `python -c "from app.config import Config; print(Config().ai_search_endpoint)"` prints the endpoint.
- The AI Search connection test no longer errors with endpoint None.
- pytest -q passes.
Return full updated contents for modified/new files.
