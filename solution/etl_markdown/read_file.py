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

        # If we got here: hard fail with helpful snippet
        snippet = line[:200]
        raise RuntimeError(
            f"Invalid JSON at {path} line {i}. "
            f"Make sure it is valid JSON (double quotes). Offending line starts with: {snippet}"
        )


# -----------------------------
# Azure OpenAI (MSI)
# -----------------------------
def get_aoai_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=_env("AZURE_OPENAI_ENDPOINT", required=True),
        api_version=_env("AZURE_OPENAI_API_VERSION", "2024-06-01"),
        azure_ad_token_provider=get_aoai_token_provider(),
    )


def get_embedding_deployment() -> str:
    return _env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", required=True)


def embed_once(client: AzureOpenAI, text: str) -> List[float]:
    dep = get_embedding_deployment()
    try:
        resp = client.embeddings.create(model=dep, input=text)
        return resp.data[0].embedding  # type: ignore[attr-defined]
    except Exception as e:
        raise RuntimeError(
            f"Embedding call failed. Check AZURE_OPENAI_EMBEDDING_DEPLOYMENT='{dep}', "
            f"AZURE_OPENAI_ENDPOINT and RBAC (Cognitive Services OpenAI User). Error: {e}"
        )


# -----------------------------
# Azure Search (MSI)
# -----------------------------
def get_index_client() -> SearchIndexClient:
    return SearchIndexClient(endpoint=_env("AZURE_SEARCH_ENDPOINT", required=True), credential=get_msi_credential())


def get_data_client(index_name: str) -> SearchClient:
    return SearchClient(endpoint=_env("AZURE_SEARCH_ENDPOINT", required=True), index_name=index_name, credential=get_msi_credential())


# -----------------------------
# Index schema (combined for table + relationship docs)
# -----------------------------
def build_index(index_name: str, vector_dim: int) -> SearchIndex:
    fields: List[SearchField] = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True, sortable=True),
        SimpleField(name="raw_id", type=SearchFieldDataType.String, filterable=True, sortable=False),

        SimpleField(name="doc_type", type=SearchFieldDataType.String, filterable=True, sortable=True),

        # Common table-ish fields
        SimpleField(name="schema_name", type=SearchFieldDataType.String, filterable=True, sortable=True, facetable=True),
        SimpleField(name="table_name", type=SearchFieldDataType.String, filterable=True, sortable=True, facetable=True),
        SimpleField(name="column_name", type=SearchFieldDataType.String, filterable=True, sortable=True),

        SearchField(name="table_business_name", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="table_business_description", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="grain", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="primary_keys", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="default_filters", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="notes", type=SearchFieldDataType.String, searchable=True),

        # Relationship fields
        SimpleField(name="from_schema", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="from_table", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="to_schema", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="to_table", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="join_type", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SearchField(name="join_keys", type=SearchFieldDataType.String, searchable=True),
        SimpleField(name="cardinality", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SearchField(name="relationship_description", type=SearchFieldDataType.String, searchable=True),
        SimpleField(name="active", type=SearchFieldDataType.Boolean, filterable=True, sortable=True),

        # Searchable content & vector
        SearchField(name="content", type=SearchFieldDataType.String, searchable=True),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=vector_dim,
            vector_search_profile_name="vprofile",
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
        profiles=[VectorSearchProfile(name="vprofile", algorithm_configuration_name="hnsw")],
    )

    return SearchIndex(name=index_name, fields=fields, vector_search=vector_search)


# -----------------------------
# Normalize docs
# -----------------------------
def normalize_table_doc(raw: Dict[str, Any]) -> Dict[str, Any]:
    raw_id = str(raw.get("id") or f"table.{raw.get('schema_name','')}.{raw.get('table_name','')}")
    return {
        "id": make_safe_key(raw_id),
        "raw_id": raw_id,
        "doc_type": "table",
        "schema_name": raw.get("schema_name"),
        "table_name": raw.get("table_name"),
        "column_name": raw.get("column_name"),
        "table_business_name": raw.get("table_business_name"),
        "table_business_description": raw.get("table_business_description"),
        "grain": raw.get("grain"),
        "primary_keys": raw.get("primary_keys"),
        "default_filters": raw.get("default_filters"),
        "notes": raw.get("notes"),
        "content": raw.get("content") or "",
        # relationship fields blank
        "from_schema": None,
        "from_table": None,
        "to_schema": None,
        "to_table": None,
        "join_type": None,
        "join_keys": None,
        "cardinality": None,
        "relationship_description": None,
        "active": None,
    }


def normalize_relationship_doc(raw: Dict[str, Any]) -> Dict[str, Any]:
    raw_id = str(raw.get("id") or f"rel.{raw.get('from_schema','')}.{raw.get('from_table','')}.to.{raw.get('to_schema','')}.{raw.get('to_table','')}")
    return {
        "id": make_safe_key(raw_id),
        "raw_id": raw_id,
        "doc_type": "relationship",
        "schema_name": raw.get("from_schema") or raw.get("schema_name"),
        "table_name": raw.get("from_table") or raw.get("table_name"),
        "column_name": None,

        "table_business_name": None,
        "table_business_description": None,
        "grain": None,
        "primary_keys": None,
        "default_filters": None,
        "notes": None,

        "from_schema": raw.get("from_schema"),
        "from_table": raw.get("from_table"),
        "to_schema": raw.get("to_schema"),
        "to_table": raw.get("to_table"),
        "join_type": raw.get("join_type"),
        "join_keys": raw.get("join_keys"),
        "cardinality": raw.get("cardinality"),
        "relationship_description": raw.get("relationship_description"),
        "active": bool(raw.get("active", True)),

        "content": raw.get("content") or "",
    }


# -----------------------------
# Drop indices helpers
# -----------------------------
LEGACY_V2_INDICES = [
    "meta_data_table_v2",
    "meta_data_vector_v2",
    "meta_data_field_v2",
    "meta_data_table",
    "meta_data_field",
]


def drop_index_if_exists(index_client: SearchIndexClient, name: str) -> bool:
    try:
        index_client.get_index(name)
    except ResourceNotFoundError:
        return False
    index_client.delete_index(name)
    return True


def drop_legacy_indices(index_client: SearchIndexClient) -> None:
    for idx in LEGACY_V2_INDICES:
        try:
            dropped = drop_index_if_exists(index_client, idx)
            if dropped:
                print(f"✅ Dropped index: {idx}")
        except Exception as e:
            print(f"⚠️ Could not drop {idx}: {e}")


# -----------------------------
# Upload helpers
# -----------------------------
def chunked(items: List[Dict[str, Any]], size: int) -> Iterable[List[Dict[str, Any]]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def upload_docs(search_client: SearchClient, docs: List[Dict[str, Any]], batch_size: int = 500) -> None:
    total = 0
    for batch in chunked(docs, batch_size):
        results = search_client.upload_documents(batch)
        failed = [r for r in results if not r.succeeded]  # type: ignore[attr-defined]
        total += len(batch)
        if failed:
            first = failed[0]
            raise RuntimeError(f"Upload failed for some docs. Example key={first.key} error={first.error_message}")
        print(f"   ✅ Uploaded {total}/{len(docs)}")


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    index_name = _env("AZURE_SEARCH_INDEX_NAME", "meta_data_field_v3")
    table_path = _env("TABLE_DOCS_PATH", "data/json_metadata/table_docs.jsonl")
    rel_path = _env("REL_DOCS_PATH", "data/json_metadata/relationship_docs.jsonl")

    drop_v2 = _env_bool("DROP_LEGACY_V2", "true")
    force_recreate = _env_bool("FORCE_RECREATE_INDEX", "false")
    batch_size = int(_env("UPLOAD_BATCH_SIZE", "500"))

    index_client = get_index_client()

    if drop_v2:
        drop_legacy_indices(index_client)

    # MSI AOAI client
    aoai = get_aoai_client()

    # Probe embedding dim so we never mismatch
    probe_vec = embed_once(aoai, "dimension probe")
    vector_dim = len(probe_vec)
    print(f"✅ Embedding vector dimension detected: {vector_dim}")

    # Recreate index if requested
    if force_recreate:
        try:
            drop_index_if_exists(index_client, index_name)
            print(f"✅ Recreated (deleted) index: {index_name}")
        except Exception as e:
            print(f"⚠️ Could not delete {index_name}: {e}")

    # Create or update index
    idx = build_index(index_name, vector_dim)
    try:
        index_client.create_or_update_index(idx)
        print(f"✅ Created/Updated index: {index_name}")
    except HttpResponseError as e:
        raise RuntimeError(
            f"Index create/update failed (common cause: trying to change existing 'id' field). "
            f"Set FORCE_RECREATE_INDEX=true and rerun. Error: {e}"
        )

    search_client = get_data_client(index_name)

    # Read docs
    docs: List[Dict[str, Any]] = []
    print(f"📄 Reading tables: {table_path}")
    for raw in read_json_objects(table_path):
        docs.append(normalize_table_doc(raw))

    print(f"📄 Reading relationships: {rel_path}")
    for raw in read_json_objects(rel_path):
        docs.append(normalize_relationship_doc(raw))

    if not docs:
        raise RuntimeError("No documents loaded. Check your TABLE_DOCS_PATH / REL_DOCS_PATH content.")

    # Embed content
    print("🧠 Creating embeddings...")
    for i, d in enumerate(docs, start=1):
        text = d.get("content") or ""
        vec = embed_once(aoai, text)
        if len(vec) != vector_dim:
            raise RuntimeError(f"Embedding dim mismatch at doc raw_id={d.get('raw_id')}: got {len(vec)} expected {vector_dim}")
        d["content_vector"] = vec
        if i % 200 == 0:
            print(f"   ...embedded {i}/{len(docs)}")

    # Upload
    print("🚀 Uploading documents to Azure AI Search...")
    upload_docs(search_client, docs, batch_size=batch_size)
    print("✅ Done.")


if __name__ == "__main__":
    main()
