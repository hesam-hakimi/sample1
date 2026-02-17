from __future__ import annotations

import os
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv(override=True)

# Azure OpenAI (recommended)
def get_openai_client():
    """
    Returns an Azure OpenAI client using either:
    - API Key (AZURE_OPENAI_API_KEY) OR
    - AAD token (DefaultAzureCredential) if key is not provided.
    """
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21").strip()

    if not endpoint:
        raise RuntimeError("Missing AZURE_OPENAI_ENDPOINT in .env")

    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()

    # v1 OpenAI Python SDK style
    try:
        from openai import AzureOpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "openai package not installed or AzureOpenAI not available. "
            "Install/upgrade: pip install -U openai"
        ) from e

    if api_key:
        return AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)

    # AAD token auth (managed identity / az login)
    try:
        from azure.identity import DefaultAzureCredential  # type: ignore
        from azure.identity import get_bearer_token_provider  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "azure-identity not installed. Install: pip install -U azure-identity"
        ) from e

    credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)
    token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")

    return AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider,
        api_version=api_version,
    )


def get_openai_chat_deployment() -> str:
    name = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "").strip()
    if not name:
        raise RuntimeError("Missing AZURE_OPENAI_CHAT_DEPLOYMENT in .env")
    return name


def get_openai_embedding_deployment() -> str:
    name = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "").strip()
    if not name:
        raise RuntimeError("Missing AZURE_OPENAI_EMBEDDING_DEPLOYMENT in .env")
    return name


def get_embedding(text: str) -> List[float]:
    client = get_openai_client()
    emb_model = get_openai_embedding_deployment()
    # input can be string
    resp = client.embeddings.create(model=emb_model, input=text)
    return resp.data[0].embedding


def chat_completion(prompt: str, temperature: float = 0.0) -> str:
    client = get_openai_client()
    model = get_openai_chat_deployment()
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return (resp.choices[0].message.content or "").strip()
