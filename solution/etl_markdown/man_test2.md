Create an Azure OpenAI client wrapper that uses ManagedIdentityCredential and get_bearer_token_provider exactly like this pattern:

token_provider = get_bearer_token_provider(ManagedIdentityCredential(), "https://cognitiveservices.azure.com/.default")
client = AzureOpenAI(
  azure_endpoint=AZURE_OPENAI_ENDPOINT,
  api_version=AZURE_OPENAI_API_VERSION,
  azure_ad_token_provider=token_provider,
)

Implement:
- app/llm_client.py:
  - class LLMClient with method:
    chat(system_prompt: str, user_prompt: str, temperature: float = 0, max_tokens: int = 800) -> str
  - It must call: client.chat.completions.create(...)
  - Model must be the deployment name from config: AZURE_OPENAI_DEPLOYMENT
  - Must return message content string
  - Add a helper:
    extract_json(text: str) -> dict
    - robustly extract JSON object from text (handles extra text around it)
    - raise ValueError with a helpful message if parsing fails

Add tests:
- tests/test_llm_client.py:
  - Mock the AzureOpenAI client response object
  - Test extract_json handles:
    1) pure JSON
    2) JSON wrapped with explanation text
    3) invalid JSON -> raises ValueError
