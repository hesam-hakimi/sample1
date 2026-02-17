# create_meta_data_vector_index.py (only the parts that change)

import os
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from openai import AzureOpenAI

from auth_utils import get_msi_credential, get_aoai_token_provider


def _env(name: str, default: str = "", required: bool = False) -> str:
    v = os.getenv(name, default).strip()
    if required and not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def get_index_client() -> SearchIndexClient:
    return SearchIndexClient(
        endpoint=_env("AZURE_SEARCH_ENDPOINT", required=True),
        credential=get_msi_credential(),
    )


def get_data_client() -> SearchClient:
    return SearchClient(
        endpoint=_env("AZURE_SEARCH_ENDPOINT", required=True),
        index_name=_env("AZURE_SEARCH_INDEX_NAME", "meta_data_field_v3"),
        credential=get_msi_credential(),
    )


def get_aoai_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=_env("AZURE_OPENAI_ENDPOINT", required=True),
        api_version=_env("AZURE_OPENAI_API_VERSION", "2024-06-01"),
        azure_ad_token_provider=get_aoai_token_provider(),  # ✅ MSI token
    )
