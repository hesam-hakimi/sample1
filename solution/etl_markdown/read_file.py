# create_metadata_vector_index.py
"""
One-time (or occasional) admin script:
1) Creates/updates a vector-enabled Azure AI Search index for FIELD-level metadata.
2) Uploads documents after building a strong `content` string + `content_vector` embedding.

Run:
  python create_metadata_vector_index.py --input metadata.jsonl

Input format (JSONL): one JSON object per line. Recommended keys:
  schema_name, table_name, column_name, business_name, business_description,
  data_type, allowed_values, notes, pii, pci, is_key, is_filter_hint, mal_code, security_classification_candidate
"""

import os
import json
import argparse
from typing import Dict, List, Iterable, Any, Optional

from dotenv import load_dotenv

from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
from azure.core.credentials import AzureKeyCredential

from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
)

# ---- Your existing embedding helper ----
# Must expose: get_embedding(text: str) -> List[float]
from embedding_utils import get_embedding  # <- keep your current implementation


def get_credential():
    """
    Prefer MSI (User-Assigned) in Azure; fall back to DefaultAzureCredential for local dev.
    If you use API key instead, set AISEARCH_API_KEY in .env
    """
    api_key = os.getenv("AISEARCH_API_KEY")
    if api_key:
        return AzureKeyCredential(api_key)

    client_id = os.getenv("CLIENT_ID")  # user-assigned managed identity client id
    if client_id:
        return ManagedIdentityCredential(client_id=client_id)

    return DefaultAzureCredential(exclude_interactive_browser_credential=False)


def chunked(items: List[Dict[str, Any]], size: int) -> Iterable[List[Dict[str, Any]]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def safe_bool(v: Any) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in {"true", "1", "yes", "y"}:
            return True
        if s in {"false", "0", "no", "n"}:
            return False
    if isinstance(v, (int, float)):
        return bool(v)
    return None


def build_content(doc: Dict[str, Any]) -> str:
    """
    The SINGLE most important thing: build a strong search string (keyword + semantic).
    """
    parts = []

    schema = doc.get("schema_name") or ""
    table = doc.get("table_name") or ""
    column = doc.get("column_name") or ""

    if schema or table or column:
        parts.append(f"schema={schema} table={table} column={column}".strip())

    # business meaning
    bn = doc.get("business_name") or ""
    bd = doc.get("business_description") or ""
    if bn:
        parts.append(f"business_name={bn}")
    if bd:
        parts.append(f"business_description={bd}")

    # technical metadata
    dt = doc.get("data_type") or ""
    av = doc.get("allowed_values") or ""
    notes = doc.get("notes") or ""
    if dt:
        parts.append(f"data_type={dt}")
    if av:
        parts.append(f"allowed_values={av}")
    if notes:
        parts.append(f"notes={notes}")

    # tags as plain text so keyword search works too
    pii = safe_bool(doc.get("pii"))
    pci = safe_bool(doc.get("pci"))
    is_key = safe_bool(doc.get("is_key"))
    is_filter_hint = safe_bool(doc.get("is_filter_hint"))
    tags = []
    if pii is not None:
        tags.append(f"pii={str(pii).lower()}")
    if pci is not None:
        tags.append(f"pci={str(pci).lower()}")
    if is_key is not None:
        tags.append(f"is_key={str(is_key).lower()}")
    if is_filter_hint is not None:
        tags.append(f"is_filter_hint={str(is_filter_hint).lower()}")
    if tags:
        parts.append("tags: " + " ".join(tags))

    # optional compliance/security
    sc = doc.get("security_classification_candidate") or ""
    if sc:
        parts.append(f"security_classification_candidate={sc}")

    return "\n".join([p for p in parts if p]).strip()


def normalize_doc(raw: Dict[str, Any], idx: int) -> Dict[str, Any]:
    # Stable, deterministic id if not provided
    schema = raw.get("schema_name") or ""
    table = raw.get("table_name") or ""
    column = raw.get("column_name") or ""
    rid = raw.get("id") or f"{schema}.{table}.{column}".strip(".") or f"row_{idx}"

    doc = {
        "id": str(rid),

        "schema_name": schema or None,
        "table_name": table or None,
        "column_name": column or None,

        "business_name": raw.get("business_name") or None,
        "business_description": raw.get("business_description") or None,

        "data_type": raw.get("data_type") or None,
        "allowed_values": raw.get("allowed_values") or None,
        "notes": raw.get("notes") or None,

        "mal_code": raw.get("mal_code") or None,
        "security_classification_candidate": raw.get("security_classification_candidate") or None,

        "pii": safe_bool(raw.get("pii")),
        "pci": safe_bool(raw.get("pci")),
        "is_key": safe_bool(raw.get("is_key")),
        "is_filter_hint": safe_bool(raw.get("is_filter_hint")),
    }

    content = build_content(doc)
    doc["content"] = content
    doc["content_vector"] = get_embedding(content)
    return doc


def create_or_update_index(index_client: SearchIndexClient, index_name: str, vector_dim: int) -> None:
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True, sortable=False),

        # Hybrid retrieval anchor (keyword)
        SearchField(name="content", type=SearchFieldDataType.String, searchable=True),

        # Vector field (semantic)
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=vector_dim,
            vector_search_profile_name="vector-profile",
        ),

        # Structured metadata for select/filter/formatting
        SearchField(name="schema_name", type=SearchFieldDataType.String, filterable=True, facetable=True, sortable=True),
        SearchField(name="table_name", type=SearchFieldDataType.String, filterable=True, facetable=True, sortable=True),
        SearchField(name="column_name", type=SearchFieldDataType.String, filterable=True, facetable=True, sortable=True),

        SearchField(name="business_name", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="business_description", type=SearchFieldDataType.String, searchable=True),

        SearchField(name="data_type", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchField(name="allowed_values", type=SearchFieldDataType.String, searchable=True),
        SearchField(name="notes", type=SearchFieldDataType.String, searchable=True),

        SearchField(name="mal_code", type=SearchFieldDataType.String, filterable=True),
        SearchField(name="security_classification_candidate", type=SearchFieldDataType.String, filterable=True),

        SimpleField(name="pii", type=SearchFieldDataType.Boolean, filterable=True, facetable=True),
        SimpleField(name="pci", type=SearchFieldDataType.Boolean, filterable=True, facetable=True),
        SimpleField(name="is_key", type=SearchFieldDataType.Boolean, filterable=True, facetable=True),
        SimpleField(name="is_filter_hint", type=SearchFieldDataType.Boolean, filterable=True, facetable=True),
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
        profiles=[VectorSearchProfile(name="vector-profile", algorithm_configuration_name="hnsw")],
    )

    index = SearchIndex(name=index_name, fields=fields, vector_search=vector_search)
    index_client.create_or_update_index(index)


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    docs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            docs.append(json.loads(line))
    return docs


def main():
    load_dotenv(override=True)

    aisearch_account = os.getenv("AISEARCH_ACCOUNT")
    index_name = os.getenv("INDEX_NAME", "meta_data_field_v2")
    vector_dim = int(os.getenv("VECTOR_DIM", "1536"))  # must match your embedding model
    batch_size = int(os.getenv("UPLOAD_BATCH", "500"))

    if not aisearch_account:
        raise ValueError("Missing AISEARCH_ACCOUNT in .env")

    endpoint = f"https://{aisearch_account}.search.windows.net"
    cred = get_credential()

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to metadata JSONL")
    args = parser.parse_args()

    raw = load_jsonl(args.input)
    normalized = [normalize_doc(r, i) for i, r in enumerate(raw)]

    index_client = SearchIndexClient(endpoint=endpoint, credential=cred)
    create_or_update_index(index_client, index_name=index_name, vector_dim=vector_dim)

    search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=cred)

    # upload in batches
    total = 0
    for batch in chunked(normalized, batch_size):
        res = search_client.upload_documents(batch)
        # res is a list of IndexingResult
        total += len(batch)
        print(f"Uploaded {total}/{len(normalized)}")

    print("Done.")
    print(f"Index: {index_name}")
    print(f"Endpoint: {endpoint}")


if __name__ == "__main__":
    index_name = os.getenv("INDEX_NAME", "meta_data_field")
    vector_dim = int(os.getenv("VECTOR_DIM", "1536"))

    final_index_name = ensure_index_vector_enabled(index_client, index_name, vector_dim)
    search_client = SearchClient(endpoint=endpoint, index_name=final_index_name, credential=cred)

    print(f"Using index: {final_index_name}")

