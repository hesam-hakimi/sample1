from __future__ import annotations

import ast
import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from openai import AzureOpenAI

from auth_utils import get_aoai_token_provider, get_msi_credential


# -----------------------------
# Env helpers
# -----------------------------
def _env(name: str, default: str = "", required: bool = False) -> str:
    v = (os.getenv(name, default) or "").strip()
    if required and not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def _env_bool(name: str, default: str = "false") -> bool:
    return _env(name, default).lower() in ("1", "true", "yes", "y")


# -----------------------------
# Safe key for Azure Search doc key
# -----------------------------
def make_safe_key(raw_key: str) -> str:
    """
    Azure Search key rules are strict. Dots/spaces/etc fail.
    Use deterministic URL-safe base64 (no padding).
    """
    b = raw_key.encode("utf-8", errors="ignore")
    s = base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")
    # keep it under 1024 chars just in case
    return s[:1024]


# -----------------------------
# Robust JSON reader
# Supports:
#  - JSONL (one object per line)
#  - JSON array file
#  - "almost JSON" lines (python dict) via ast.literal_eval
# -----------------------------
def read_json_objects(path: str) -> Iterable[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")

    text = p.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return

    # Try JSON array first
    if text.startswith("["):
        try:
            arr = json.loads(text)
            if isinstance(arr, list):
                for obj in arr:
                    if isinstance(obj, dict):
                        yield obj
                return
        except Exception:
            pass

    # Else treat as JSONL / line-based
    for i, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # best: proper JSON
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                yield obj
            continue
        except json.JSONDecodeError:
            pass

        # fallback: python dict syntax (single quotes, True/False, etc.)
        try:
            obj2 = ast.literal_eval(line)
            if isinstance(obj2, dict):
                yield obj2
                continue
        except Exception:
            pass

        # If we
