from __future__ import annotations

import os
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from dotenv import load_dotenv

from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
)

from ai_utils import get_msi_credential, get_aoai_client, embed_text

load_dotenv()


# ----------------------------
# Robust JSON reader
# ----------------------------
def read_json_objects(path: str) -> Iterable[Dict[str, Any]]:
    """
    Reads:
    - JSONL (one object per line)
    - pretty-printed multi-line objects
    - JSON arrays
    - concatenated JSON objects
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing file: {p}")

    raw = p.read_text(encoding="utf-8").strip()
    if not raw:
        return []

    # If array
    if raw.lstrip().startswith("["):
        data = json.loads(raw)
        if isinstance(data, list):
            for obj in data:
                if isinstance(obj, dict):
                    yield obj
        return

    # Try line-by-line JSONL
    ok_any = False
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                ok_any = True
                yield obj
        except Exception:
            ok_any = False
            break
    if ok_any:
        return

    # Fallback: streaming decode concatenated objects
    decoder = json.JSONDecoder()
    idx = 0
    n = len(raw)
    while idx < n:
        while idx < n and raw[idx].isspace():
            idx += 1
        if idx >= n:
            break
        obj, end = decoder.raw_decode(raw, idx)
        idx = end
        if isinstance(obj, dict):
            yield obj


def make_safe_key(raw_key: str) -> str:
    # Azure Search key constraints: no slashes, etc. We'll keep it simple but stable.
    # Replace whitespace with underscore, strip, and cap length.
    s = (raw_key or "").strip().replace(" ", "_")
    s = s.replace("/", "_").replace("\\", "_")
    return s[:900] if len(s) > 900 else s


def build_table_content(raw: Dict[str, Any]) -> str:
    parts = []
    parts.append(f"Schema: {raw.get('schema_name','')}")
    parts.append(f"Table: {raw.get('table_name','')}")
    parts.append(f"Business Name: {raw.get('table_business_name','')}")
    parts.append(f"Description: {raw.get('table_business_description','')}")
    parts.append(f"Grain: {raw.get('grain','')}")
    parts.append(f"Primary Keys: {raw.get('primary_keys','')}")
    parts.append(f"Default Filters: {raw.get('default_filters','')}")
    parts.append(f"Notes: {raw.get('notes','')}")
    return "\n".join([p for p in parts if p and p.strip()])


def build_field_content(raw: Dict[str, Any]) -> str:
    parts = []
    parts.append(f"Schema: {raw.get('schema_name','')}")
    parts.append(f"Table: {raw.get('table_name','')}")
    parts.append(f"Column: {raw.get('column_name','')}")
    parts.append(f"Business Name: {raw.get('business_name','')}")
    parts.append(f"Description: {raw.get('business_description','')}")
    parts.append(f"Data Type: {raw.get('data_type','')}")
    parts.append(f"MAL Code: {raw.get('mal_code','')}")
    # common tags if present
    for k in ("pii","pci","is_key","is_filter_hint","security_classification_candidate"):
        if k in raw:
            parts.append(f"{k}: {raw.get(k)}")
    return "\n".join([p for p in parts if p and str(p).strip()])


def build_relationship_content(raw: Dict[str, Any]) -> str:
    parts = []
    parts.append(f"FROM {raw.get('from_schema','')}.{raw.get('from_table','')}")
    parts.append(f"TO {raw.get('to_schema','')}.{raw.get('to_table','')}")
    parts.append(f"Join type: {raw.get('join_type','')}")
    parts.append(f"Join keys: {raw.get('join_keys','')}")
    parts.append(f"Cardinality: {raw.get('cardinality','')}")
    parts.append(f"Description: {raw.get('relationship_description','')}")
    parts.append(f"Active: {raw.get('active', True)}")
    return "\n".join([p for p in parts if p and str(p).strip()])


def normalize_doc(doc_type: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    schema_name = raw.get("schema_name") or raw.get("from_schema") or ""
    table_name = raw.get("table_name") or raw.get("from_table") or ""
    column_name = raw.get("column_name") or ""
    raw_id = raw.get("id") or f"{doc_type}.{schema_name}.{table_name}.{column_name}".strip(".")
    raw_id = str(raw_id)

    if doc_type == "table":
        content = raw.get("content") or build_table_content(raw)
    elif doc_type == "relationship":
        content = raw.get("content") or build_relationship_content(raw)
    else:
        content = raw.get("content") or build_field_content(raw)

    out = {
        "id": make_safe_key(raw_id),
        "doc_type": doc_type,
        "raw_id": raw_id,
        "schema_name": raw.get("schema_name") or raw.get("from_schema"),
        "table_name": raw.get("table_name") or raw.get("from_table"),
        "column_name": raw.get("column_name"),
        # relationship-specific
        "from_schema": raw.get("from_schema"),
        "from_table": raw.get("from_table"),
        "to_schema": raw.get("to_schema"),
        "to_table": raw.get("to_table"),
        "join_type": raw.get("join_type"),
        "join_keys": raw.get("join_keys"),
        "cardinality": raw.get("cardinality"),
        "active": raw.get("active"),
        # field/table specifics (best effort)
        "business_name": raw.get("business_name") or raw.get("table_business_name"),
        "business_description": raw.get("business_description") or raw.get("table_business_description"),
        "data_type": raw.get("data_type"),
        "mal_code": raw.get("mal_code"),
        "content": content,
    }
    return out


def drop_indexes(index_client: SearchIndexClient, names: List[str]) -> None:
    existing = {idx.name for idx in index_client.list_indexes()}
    for n in names:
        if n in existing:
            index_client.delete_index(n)
            print(f"✅ Dropped index: {n}")


def ensure_index(index_client: SearchIndexClient, index_name: str, vector_dim: int) -> None:
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True, sortable=False),
        SimpleField(name="doc_type", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="raw_id", type=SearchFieldDataType.String, filterable=False),
        SimpleField(name="schema_name", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="table_name", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="column_name", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="from_schema", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="from_table", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="to_schema", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="to_table", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="join_type", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="join_keys", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SimpleField(name="cardinality", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="active", type=SearchFieldDataType.Boolean, filterable=True),
        SearchableField(name="business_name", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SearchableField(name="business_description", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SimpleField(name="data_type", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="mal_code", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=int(vector_dim),
            vector_search_profile_name="vprofile",
        ),
    ]

    vs = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
        profiles=[VectorSearchProfile(name="vprofile", algorithm_configuration_name="hnsw")],
    )

    index = SearchIndex(name=index_name, fields=fields, vector_search=vs)
    index_client.create_or_update_index(index)
    print(f"✅ Ensured index '{index_name}' with vector_dim={vector_dim}")


def batched(lst: List[Any], n: int) -> Iterable[List[Any]]:
    for i in range(0, len(lst), n):
        yield lst[i:i+n]


def main() -> None:
    index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "meta_data_v3").strip()

    field_path = os.getenv("FIELD_DOCS_PATH", "data/json_metadata/field_docs.jsonl").strip()
    table_path = os.getenv("TABLE_DOCS_PATH", "data/json_metadata/table_docs.jsonl").strip()
    rel_path = os.getenv("REL_DOCS_PATH", "data/json_metadata/relationship_docs.jsonl").strip()

    cred = get_msi_credential()
    aoai = get_aoai_client(cred)

    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "").strip()
    if not endpoint:
        raise RuntimeError("AZURE_SEARCH_ENDPOINT is missing in .env")

    index_client = SearchIndexClient(endpoint=endpoint, credential=cred)
    search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=cred)

    # Drop older v2/v3 variants if requested
    drop_list = [
        "meta_data_table_v2",
        "meta_data_vector_v2",
        "meta_data_field",
        "meta_data_table",
        "meta_data_field_v3",
    ]
    drop_indexes(index_client, drop_list)

    print(f"📥 Reading fields: {field_path}")
    field_docs = [normalize_doc("field", obj) for obj in read_json_objects(field_path)]

    print(f"📥 Reading tables: {table_path}")
    table_docs = [normalize_doc("table", obj) for obj in read_json_objects(table_path)]

    print(f"📥 Reading relationships: {rel_path}")
    rel_docs = [normalize_doc("relationship", obj) for obj in read_json_objects(rel_path)]

    docs = field_docs + table_docs + rel_docs

    # Probe embedding dimension (prevents 1536 vs 1024 mismatch)
    emb_deploy = os.getenv("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT", "").strip()
    if not emb_deploy:
        raise RuntimeError("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT is missing in .env")

    desired_dim_env = os.getenv("VECTOR_DIM", "").strip()
    desired_dim = int(desired_dim_env) if desired_dim_env else None

    # Probe
    try:
        probe = embed_text(aoai, "probe", emb_deploy, desired_dim=desired_dim)
    except Exception:
        # retry once (covers recent deployment warmup issues)
        time.sleep(2)
        probe = embed_text(aoai, "probe", emb_deploy, desired_dim=desired_dim)

    vector_dim = len(probe)
    print(f"🔎 Embedding probe dimension = {vector_dim}")

    ensure_index(index_client, index_name, vector_dim=vector_dim)

    # Embed documents in batches
    print("🧠 Creating embeddings...")
    for batch in batched(docs, 16):
        # Embed each content (simple loop; safe + clear)
        for d in batch:
            d["content_vector"] = embed_text(aoai, d.get("content","") or " ", emb_deploy, desired_dim=vector_dim)
        # small pacing to be friendly; adjust/remove as desired
        # time.sleep(0.05)

    # Upload
    print("⬆️ Uploading documents...")
    for batch in batched(docs, 500):
        res = search_client.upload_documents(documents=batch)
        failed = [r for r in res if not r.succeeded]
        if failed:
            print(f"⚠️ Upload failures: {len(failed)} (showing first 3)")
            for f in failed[:3]:
                print(f" - key={f.key} error={getattr(f,'error_message', None)}")
        else:
            print(f"✅ Uploaded {len(batch)} docs")

    print("✅ Done.")


if __name__ == "__main__":
    main()
