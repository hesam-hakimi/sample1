# Azure AI Search: Drop `v2`, Recreate with Correct Vector Dim, and Upload Clean Docs

This markdown gives you copy-paste code to:

1) **Drop** the `meta_data_field_v2` index  
2) **Create** a fresh index with the **correct vector dimension** (auto-detected from your embedding function)  
3) **Upload** documents with:
   - a **safe** `id` (Base64 URL-safe)
   - optional `raw_id` for debugging
   - `content` + `content_vector` for **hybrid retrieval**

---

## 0) What this fixes

### ✅ Fix #1 — Vector dimension mismatch
Your index was created with **1536**, but your embedding function returns **1024**.
This code **auto-detects** the dimension (`len(get_embedding("x"))`) and creates the index correctly.

### ✅ Fix #2 — Invalid document key
Your previous `id` had dots (`.`). This code encodes the key into **URL-safe Base64**.

### ✅ Fix #3 — Uploading fields not in index
If you upload `raw_id`, the index must define it. This code defines it.

---

## 1) Copy-paste: Drop index + Create index + Upload docs

> Put this in your `create_meta_data_vector_index.py` (or replace the main parts with this).

```python
import os
import json
import base64
import argparse
from typing import Any, Dict, List, Iterable, Optional

from dotenv import load_dotenv

from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError

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
# Must return a python list[float]
from embedding_utils import get_embedding


# ----------------------------
# Credentials / Clients
# ----------------------------
def get_credential():
    """
    Prefer:
      - API key if AISEARCH_API_KEY is set
      - Managed Identity if CLIENT_ID is set
      - else DefaultAzureCredential (good for local dev)
    """
    api_key = os.getenv("AISEARCH_API_KEY")
    if api_key:
        return AzureKeyCredential(api_key)

    client_id = os.getenv("CLIENT_ID")
    if client_id:
        return ManagedIdentityCredential(client_id=client_id)

    return DefaultAzureCredential(exclude_interactive_browser_credential=False)


def get_endpoint() -> str:
    aisearch_account = os.getenv("AISEARCH_ACCOUNT")
    if not aisearch_account:
        raise ValueError("Missing AISEARCH_ACCOUNT in .env")
    return f"https://{aisearch_account}.search.windows.net"


# ----------------------------
# Utils
# ----------------------------
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


def make_safe_key(raw_key: str) -> str:
    """
    Azure AI Search key rules: letters/digits/_/-/= only.
    URL-safe Base64 yields A-Z a-z 0-9 _ - and may include '=' padding (allowed).
    """
    b = raw_key.encode("utf-8")
    return base64.urlsafe_b64encode(b).decode("ascii")


def build_content(doc: Dict[str, Any]) -> str:
    """
    Make a strong text field for hybrid retrieval (keyword + semantic).
    """
    parts = []

    schema = doc.get("schema_name") or ""
    table = doc.get("table_name") or ""
    column = doc.get("column_name") or ""

    if schema or table or column:
        parts.append(f"schema={schema} table={table} column={column}".strip())

    bn = doc.get("business_name") or ""
    bd = doc.get("business_description") or ""
    if bn:
        parts.append(f"business_name={bn}")
    if bd:
        parts.append(f"business_description={bd}")

    dt = doc.get("data_type") or ""
    av = doc.get("allowed_values") or ""
    notes = doc.get("notes") or ""
    if dt:
        parts.append(f"data_type={dt}")
    if av:
        parts.append(f"allowed_values={av}")
    if notes:
        parts.append(f"notes={notes}")

    pii = doc.get("pii")
    pci = doc.get("pci")
    is_key = doc.get("is_key")
    is_filter_hint = doc.get("is_filter_hint")
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

    sc = doc.get("security_classification_candidate") or ""
    if sc:
        parts.append(f"security_classification_candidate={sc}")

    return "\n".join([p for p in parts if p]).strip()


def normalize_doc(raw: Dict[str, Any], idx: int) -> Dict[str, Any]:
    schema = raw.get("schema_name") or ""
    table = raw.get("table_name") or ""
    column = raw.get("column_name") or ""

    raw_id = raw.get("id") or f"field.{schema}.{table}.{column}".strip(".") or f"row_{idx}"
    safe_id = make_safe_key(str(raw_id))

    doc = {
        # ✅ required key (safe)
        "id": safe_id,

        # ✅ optional debug: keep original identifier
        "raw_id": str(raw_id),

        # ✅ structured fields
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

    # ✅ embedding with correct dimension (auto-detected when index is created)
    doc["content_vector"] = get_embedding(content)

    return doc


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


# ----------------------------
# Index management
# ----------------------------
def detect_vector_dim() -> int:
    v = get_embedding("dimension check")
    if not isinstance(v, list) or not v:
        raise ValueError("get_embedding() did not return a non-empty list[float].")
    dim = len(v)
    print(f"[INFO] Detected embedding dimension: {dim}")
    return dim


def drop_index_if_exists(index_client: SearchIndexClient, index_name: str) -> None:
    """
    Drop (delete) an Azure AI Search index if it exists.
    """
    try:
        index_client.get_index(index_name)
        index_client.delete_index(index_name)
        print(f"[OK] Dropped index: {index_name}")
    except ResourceNotFoundError:
        print(f"[OK] Index not found (nothing to drop): {index_name}")


def create_index(index_client: SearchIndexClient, index_name: str, vector_dim: int) -> None:
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),

        # Debug / traceability
        SearchField(name="raw_id", type=SearchFieldDataType.String, filterable=True),

        # Hybrid anchor
        SearchField(name="content", type=SearchFieldDataType.String, searchable=True),

        # Vector field
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=vector_dim,
            vector_search_profile_name="vector-profile",
        ),

        # Structured fields
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

    idx = SearchIndex(name=index_name, fields=fields, vector_search=vector_search)
    index_client.create_or_update_index(idx)
    print(f"[OK] Created index: {index_name} (dim={vector_dim})")


# ----------------------------
# Main
# ----------------------------
def main():
    load_dotenv(override=True)

    endpoint = get_endpoint()
    cred = get_credential()

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to metadata JSONL")
    parser.add_argument("--drop_v2", action="store_true", help="Drop meta_data_field_v2 before creating target index")
    args = parser.parse_args()

    # If you want to drop v2 specifically:
    drop_v2_name = "meta_data_field_v2"

    # Your target index name (new recommended)
    index_name = os.getenv("INDEX_NAME", "meta_data_field_v3")

    upload_batch = int(os.getenv("UPLOAD_BATCH", "500"))

    index_client = SearchIndexClient(endpoint=endpoint, credential=cred)

    # 1) Drop v2 (optional)
    if args.drop_v2:
        drop_index_if_exists(index_client, drop_v2_name)

    # 2) Create fresh target index with correct vector dim
    vector_dim = detect_vector_dim()

    # If target index exists and schema may conflict, you can drop it too (optional):
    # drop_index_if_exists(index_client, index_name)

    create_index(index_client, index_name, vector_dim)

    # 3) Upload docs
    raw_docs = load_jsonl(args.input)
    normalized = [normalize_doc(r, i) for i, r in enumerate(raw_docs)]

    # sanity check
    if normalized:
        print("[CHECK] content_vector length =", len(normalized[0]["content_vector"]))

    search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=cred)

    total = 0
    for batch in chunked(normalized, upload_batch):
        res = search_client.upload_documents(batch)
        total += len(batch)
        print(f"[OK] Uploaded {total}/{len(normalized)}")

    print("[DONE] Index + upload complete.")


if __name__ == "__main__":
    main()
