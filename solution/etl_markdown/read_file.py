# auth_utils.py
from __future__ import annotations

import os
from typing import Callable

from azure.identity import ManagedIdentityCredential

# Newer azure-identity versions include this helper
try:
    from azure.identity import get_bearer_token_provider  # type: ignore
except Exception:  # pragma: no cover
    get_bearer_token_provider = None


def get_msi_credential() -> ManagedIdentityCredential:
    """
    MSI-only credential:
    - Never opens a browser
    - Never uses az login
    - Never uses VS Code token cache
    """
    client_id = (os.getenv("AZURE_CLIENT_ID") or os.getenv("MANAGED_IDENTITY_CLIENT_ID") or "").strip()
    if client_id:
        return ManagedIdentityCredential(client_id=client_id)
    return ManagedIdentityCredential()  # system-assigned MI


def get_aoai_token_provider() -> Callable[[], str]:
    """
    Token provider compatible with OpenAI Python SDK AzureOpenAI(..., azure_ad_token_provider=...).
    Uses MSI to get token for Cognitive Services.
    """
    cred = get_msi_credential()
    scope = "https://cognitiveservices.azure.com/.default"

    if get_bearer_token_provider is not None:
        return get_bearer_token_provider(cred, scope)

    # Fallback for older environments
    def _provider() -> str:
        return cred.get_token(scope).token

    return _provider
