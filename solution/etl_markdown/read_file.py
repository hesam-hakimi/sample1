# Parametric `main()` (no CLI args) — Drop v2, Create target index with correct vector dim, Upload docs

Copy-paste this as your `create_meta_data_vector_index.py`.

✅ No `argparse`  
✅ `main()` is parametric: `main(input_path=..., target_index=..., drop_v2=True, drop_target=False)`  
✅ Auto-detects embedding dimension (fixes 1536 vs 1024 mismatch)  
✅ Safe `id` (fixes invalid key with dots)  
✅ Index includes `raw_id` so upload won’t fail

---

```python
import os
import json
import base64
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
# Must return list[float]
from embedding_utils import get_embedding


# ----------------------------
# Credentials / Endpoint
# ----------------------------
def get_credential():
    api_key = os.getenv("AISEARCH_API_KEY")
    if api_key:
        return AzureKeyCredential(api_key)

    client_id = os.getenv("CLIENT_ID")
    if client_id:
        return ManagedIdentityCredential(client_id=client_id)

    return DefaultAzureCredential(exclude_interactive_browser_credential=False)


def get_endpoint() -> str:
    acct = os.getenv("AISEARCH_ACCOUNT")
    if not acct:
        raise ValueError("Missing AISEARCH_ACCOUNT in .env")
    return f"https://{acct}.search.windows.net"


# ----------------------------
# Helpers
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
    URL-safe base64 yields A-Z a-z 0-9 _ - and may include '=' padding (allowed).
    """
    return base64.urlsafe_b64encode(raw_key.encode("utf-8")).decode("ascii")


def build_content(doc: Dict[str, Any]) -> str:
    """
    Strong hybrid text: helps keyword + vector retrieval.
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

    doc = {
        "id": make_safe_key(str(raw_id)),   # safe key for Azure Search
        "raw_id": str(raw_id),              # debug / trace

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


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def detect_vector_dim() -> int:
    v = get_embedding("dimension check")
    if not isinstance(v, list) or not v:
        raise ValueError("get_embedding() must return a non-empty list[float].")
    dim = len(v)
    print(f"[INFO] Detected embedding dimension: {dim}")
    return dim


# ----------------------------
# Index management
# ----------------------------
def drop_index_if_exists(index_client: SearchIndexClient, index_name: str) -> None:
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
# Parametric main (NO ARGS)
# ----------------------------
def main(
    input_path: str,
    target_index: str = "meta_data_field_v3",
    drop_v2: bool = True,
    drop_target: bool = False,
    upload_batch: int = 500,
):
    """
    Parameters:
      input_path   : path to metadata JSONL
      target_index : index to create and upload into
      drop_v2      : if True, delete 'meta_data_field_v2' first
      drop_target  : if True, delete target_index before creating it
      upload_batch : upload batch size
    """
    load_dotenv(override=True)

    endpoint = get_endpoint()
    cred = get_credential()

    index_client = SearchIndexClient(endpoint=endpoint, credential=cred)

    if drop_v2:
        drop_index_if_exists(index_client, "meta_data_field_v2")

    if drop_target:
        drop_index_if_exists(index_client, target_index)

    vector_dim = detect_vector_dim()
    create_index(index_client, target_index, vector_dim)

    raw_docs = load_jsonl(input_path)
    normalized = [normalize_doc(r, i) for i, r in enumerate(raw_docs)]

    if normalized:
        print("[CHECK] content_vector length =", len(normalized[0]["content_vector"]))

    search_client = SearchClient(endpoint=endpoint, index_name=target_index, credential=cred)

    total = 0
    for batch in chunked(normalized, upload_batch):
        search_client.upload_documents(batch)
        total += len(batch)
        print(f"[OK] Uploaded {total}/{len(normalized)}")

    print("[DONE] Index + upload complete.")
    print(f"[DONE] Target index: {target_index}")


if __name__ == "__main__":
    # ✅ change these two lines only
    main(
        input_path="metadata.jsonl",
        target_index=os.getenv("INDEX_NAME", "meta_data_field_v3"),
        drop_v2=True,
        drop_target=False,
        upload_batch=int(os.getenv("UPLOAD_BATCH", "500")),
    )
