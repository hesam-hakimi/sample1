import os
import autogen


def _env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if v is None or v.strip() == "":
        raise RuntimeError(f"Missing env var: {name}")
    return v


def build_llm_config() -> autogen.LLMConfig:
    endpoint = _env("AZURE_OPENAI_ENDPOINT")
    if not endpoint.endswith("/"):
        endpoint += "/"

    deployment = _env("AZURE_OPENAI_DEPLOYMENT")
    api_version = _env("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

    # IMPORTANT:
    # - model = Azure OpenAI deployment name
    # - base_url = Azure OpenAI endpoint
    # - azure_ad_token_provider = "DEFAULT" -> DefaultAzureCredential (MSI on Azure VM)
    return autogen.LLMConfig(
        {
            "model": deployment,
            "base_url": endpoint,
            "api_type": "azure",
            "api_version": api_version,
            "azure_ad_token_provider": "DEFAULT",
            "temperature": 0,
        }
    )


def main() -> None:
    llm_config = build_llm_config()

    assistant = autogen.AssistantAgent(
        name="assistant",
        llm_config=llm_config,
        system_message="You are a helpful assistant for your_company. Keep answers short.",
    )

    user = autogen.UserProxyAgent(
        name="user_proxy",
        human_input_mode="NEVER",
        code_execution_config=False,
    )

    user.run(assistant, message="Say hello in one short sentence.").process()


if __name__ == "__main__":
    main()
