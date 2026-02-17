from __future__ import annotations

import json
import os
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from dotenv import load_dotenv

from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SearchableField,
    SimpleField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
)

# OpenAI (Azure)
from openai import AzureOpenAI


# ---------------------------
# Helpers
# ---------------------------

def _bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


def make_safe_key(raw_id: str) -> str:
    """
    Azure Search doc key can only contain [A-Za-z0-9_-=] and must be stable.
    Use sha256 hex (safe, short, deterministic).
    """
    return hashlib.sha256(raw_id.encode("utf-8")).hexdigest()


def get_search_credential():
    """
    Prefer API key if provided; otherwise MSI/AAD.
    """
    api_key = os.getenv("AZURE_SEARCH_API_KEY", "").strip()
    if api_key:
        return api_key  # SearchClient accepts AzureKeyCredential too, but key string works via AzureKeyCredential path below
    client_id = os.getenv("AZURE_CLIENT_ID", "").strip()
    if client_id:
        return ManagedIdentityCredential(client_id=client_id)
    return DefaultAzureCredential(exclude_interactive_browser_credential=False)


def get_search_clients(endpoint: str, index_name: str):
    cred = get_search_credential()

    # If using key, wrap with AzureKeyCredential
    if isinstance(cred, str):
        from azure.core.credentials import AzureKeyCredential
        key_cred = AzureKeyCredential(cred)
        return (
            SearchIndexClient(endpoint=endpoint, credential=key_cred),
            SearchClient(endpoint=endpoint, index_name=index_name, credential=key_cred),
        )

    return (
        SearchIndexClient(endpoint=endpoint, credential=cred),
        SearchClient(endpoint=endpoint, index_name=index_name, credential=cred),
    )


def get_aoai_client() -> AzureOpenAI:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21").strip()
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()

    if not endpoint:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT is missing")

    if api_key:
        return AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)

    # AAD/MSI auth
    client_id = os.getenv("AZURE_CLIENT_ID", "").strip()
    if client_id:
        cred = ManagedIdentityCredential(client_id=client_id)
    else:
        cred = DefaultAzureCredential(exclude_interactive_browser_credential=False)

    token_provider = get_bearer_token_provider(cred, "https://cognitiveservices.azure.com/.default")
    return AzureOpenAI(azure_endpoint=endpoint, azure_ad_token_provider=token_provider, api_version=api_version)


def embed_text(client: AzureOpenAI, text: str, vector_dim: int) -> List[float]:
    dep = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "").strip()
    if not dep:
        raise RuntimeError("AZURE_OPENAI_EMBEDDING_DEPLOYMENT is missing")

    # text-embedding-3-* supports `dimensions`. If your deployment doesn’t, we fallback.
    try:
        resp = client.embeddings.create(model=dep, input=text, dimensions=vector_dim)
    except TypeError:
        resp = client.embeddings.create(model=dep, input=text)

    vec = resp.data[0].embedding
    if len(vec) != vector_dim:
        raise RuntimeError(
            f"Embedding length mismatch. Got {len(vec)} but VECTOR_DIM={vector_dim}. "
            f"Fix by setting VECTOR_DIM to {len(vec)} OR requesting embeddings with the same dimensions."
        )
    return vec


def drop_index_if_exists(index_client: SearchIndexClient, index_name: str) -> None:
    try:
        index_client.delete_index(index_name)
        print(f"✅ Dropped index: {index_name}")
    except ResourceNotFoundError:
        print(f"ℹ️ Index not found (skip drop): {index_name}")


def drop_v2_indexes(index_client: SearchIndexClient) -> None:
    """
    Drops common v2 names so you don't fight "id cannot be changed" updates.
    """
    candidates = [
        "meta_data_field_v2",
        "meta_data_table_v2",
        "meta_data_vector_v2",
        "meta_data_field",
        "meta_data_table",
    ]
    for name in candidates:
        drop_index_if_exists(index_client, name)


def build_unified_index(index_name: str, vector_dim: int) -> SearchIndex:
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SimpleField(name="raw_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="doc_type", type=SearchFieldDataType.String, filterable=True, facetable=True),

        # table/field identifiers
        SimpleField(name="schema_name", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="table_name", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="column_name", type=SearchFieldDataType.String, filterable=True, facetable=True),

        # business metadata
        SearchableField(name="business_name", type=SearchFieldDataType.String),
        SearchableField(name="business_description", type=SearchFieldDataType.String),
        SimpleField(name="data_type", type=SearchFieldDataType.String, filterable=True),

        SimpleField(name="pii", type=SearchFieldDataType.Boolean, filterable=True),
        SimpleField(name="pci", type=SearchFieldDataType.Boolean, filterable=True),
        SimpleField(name="is_key", type=SearchFieldDataType.Boolean, filterable=True),

        # relationship fields
        SimpleField(name="from_schema", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="from_table", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="to_schema", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="to_table", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="join_type", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="join_keys", type=SearchFieldDataType.String),
        SimpleField(name="cardinality", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="active", type=SearchFieldDataType.Boolean, filterable=True),

        # main text used for search + embeddings
        SearchableField(name="content", type=SearchFieldDataType.String),

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


def read_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def normalize_table_doc(raw: Dict[str, Any]) -> Dict[str, Any]:
    schema = raw.get("schema_name") or ""
    table = raw.get("table_name") or ""
    raw_id = raw.get("id") or f"table.{schema}.{table}"
    content = raw.get("content") or ""

    return {
        "raw_id": str(raw_id),
        "doc_type": "table",
        "schema_name": schema,
        "table_name": table,
        "column_name": None,
        "business_name": raw.get("table_business_name") or "",
        "business_description": raw.get("table_business_description") or "",
        "data_type": None,
        "pii": False,
        "pci": False,
        "is_key": False,
        "from_schema": None,
        "from_table": None,
        "to_schema": None,
        "to_table": None,
        "join_type": None,
        "join_keys": None,
        "cardinality": None,
        "active": None,
        "content": content,
    }


def normalize_relationship_doc(raw: Dict[str, Any]) -> Dict[str, Any]:
    raw_id = raw.get("id") or ""
    content = raw.get("content") or ""
    return {
        "raw_id": str(raw_id),
        "doc_type": "relationship",
        "schema_name": None,
        "table_name": None,
        "column_name": None,
        "business_name": "",
        "business_description": raw.get("relationship_description") or "",
        "data_type": None,
        "pii": False,
        "pci": False,
        "is_key": False,
        "from_schema": raw.get("from_schema"),
        "from_table": raw.get("from_table"),
        "to_schema": raw.get("to_schema"),
        "to_table": raw.get("to_table"),
        "join_type": raw.get("join_type"),
        "join_keys": raw.get("join_keys"),
        "cardinality": raw.get("cardinality"),
        "active": bool(raw.get("active", True)),
        "content": content,
    }


def upload_docs(search_client: SearchClient, docs: List[Dict[str, Any]], batch_size: int = 200) -> None:
    from azure.search.documents.models import IndexDocumentsBatch

    total = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i : i + batch_size]
        b = IndexDocumentsBatch()
        b.add_upload_actions(batch)
        result = search_client.index_documents(batch=b)

        failed = [r for r in result if not r.succeeded]
        if failed:
            # print first few failures
            print("❌ Some documents failed:")
            for r in failed[:10]:
                print(f"  key={r.key} error={r.error_message}")
            raise RuntimeError("Upload failed. See errors above.")
        total += len(batch)
        print(f"✅ Uploaded {total}/{len(docs)}")


def main() -> None:
    load_dotenv()

    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "").strip()
    index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "amcb_metadata_v3").strip()
    vector_dim = int(os.getenv("VECTOR_DIM", "1024").strip())

    table_path = os.getenv("TABLE_DOCS_PATH", "./json_metadata/table_docs.jsonl").strip()
    rel_path = os.getenv("RELATIONSHIP_DOCS_PATH", "./json_metadata/relationship_docs.jsonl").strip()

    recreate = _bool_env("RECREATE_INDEX", default=True)

    if not endpoint:
        raise RuntimeError("AZURE_SEARCH_ENDPOINT is missing")

    index_client, search_client = get_search_clients(endpoint, index_name)
    aoai_client = get_aoai_client()

    # 1) Drop v2 indexes (so you stop fighting schema updates)
    drop_v2_indexes(index_client)

    # 2) Recreate target index
    if recreate:
        drop_index_if_exists(index_client, index_name)

    index = build_unified_index(index_name, vector_dim)
    try:
        index_client.create_index(index)
        print(f"✅ Created index: {index_name}")
    except HttpResponseError as e:
        # If already exists and recreate=false, this is OK
        if "already exists" in str(e).lower():
            print(f"ℹ️ Index already exists: {index_name}")
        else:
            raise

    # 3) Read + normalize
    docs: List[Dict[str, Any]] = []

    print(f"📥 Reading tables: {table_path}")
    for raw in read_jsonl(table_path):
        doc = normalize_table_doc(raw)
        doc["id"] = make_safe_key(doc["raw_id"])
        docs.append(doc)

    print(f"📥 Reading relationships: {rel_path}")
    for raw in read_jsonl(rel_path):
        doc = normalize_relationship_doc(raw)
        doc["id"] = make_safe_key(doc["raw_id"])
        docs.append(doc)

    # 4) Embed content
    print("🧠 Creating embeddings...")
    for idx, d in enumerate(docs, start=1):
        d["content_vector"] = embed_text(aoai_client, d.get("content", "") or "", vector_dim)
        if idx % 200 == 0:
            print(f"  embedded {idx}/{len(docs)}")

    # 5) Upload
    print("🚀 Uploading docs...")
    upload_docs(search_client, docs, batch_size=200)

    print("🎉 Done.")


if __name__ == "__main__":
    main()
