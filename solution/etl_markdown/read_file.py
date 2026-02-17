# create_meta_data_vector_index.py
from __future__ import annotations

import os
import json
import ast
import time
import hashlib
import base64
from typing import Any, Dict, Iterable, List, Optional, Tuple

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
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError

from openai import AzureOpenAI
from openai import NotFoundError, RateLimitError, APIError

from auth_utils import get_msi_credential, get_aoai_token_provider


# ------------------------- helpers -------------------------

def _env(name: str, default: str = "", required: bool = False) -> str:
    v = (os.getenv(name) or default).strip()
    if required and not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def _env_bool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "y", "on"}


def safe_doc_id(raw_id: str) -> str:
    """
    Azure Search keys can only contain letters/digits/_/-/=.
    We generate a stable, short, safe id using sha256 + urlsafe base64.
    """
    b = hashlib.sha256(raw_id.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def build_table_content(raw: Dict[str, Any]) -> str:
    parts = []
    sch = raw.get("schema_name") or ""
    tbl = raw.get("table_name") or ""
    parts.append(f"DocType: table")
    if sch: parts.append(f"Schema: {sch}")
    if tbl: parts.append(f"Table: {tbl}")
    for k in [
        "table_business_name",
        "table_business_description",
        "grain",
        "primary_keys",
        "default_filters",
        "notes",
    ]:
        v = raw.get(k)
        if v:
            parts.append(f"{k}: {v}")
    return "\n".join(parts).strip()


def build_rel_content(raw: Dict[str, Any]) -> str:
    parts = []
    parts.append("DocType: relationship")
    parts.append(f"FROM {raw.get('from_schema','')}.{raw.get('from_table','')}")
    parts.append(f"TO   {raw.get('to_schema','')}.{raw.get('to_table','')}")
    if raw.get("join_type"):
        parts.append(f"join_type: {raw['join_type']}")
    if raw.get("join_keys"):
        parts.append(f"join_keys: {raw['join_keys']}")
    if raw.get("cardinality"):
        parts.append(f"cardinality: {raw['cardinality']}")
    if raw.get("relationship_description"):
        parts.append(f"description: {raw['relationship_description']}")
    return "\n".join(parts).strip()


def load_records(path: str) -> List[Dict[str, Any]]:
    """
    Supports:
    - JSONL (one object per line)
    - JSON array ([{...},{...}])
    - Pretty JSON objects spanning lines
    - Python-dict-like lines (fallback ast.literal_eval)
    - Lines ending with trailing commas
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    s = raw_text.strip()
    if not s:
        return []

    # Try full JSON first (array/object)
    if s.startswith("[") or (s.startswith("{") and "\n" in s):
        try:
            obj = json.loads(s)
            if isinstance(obj, list):
                return [x for x in obj if isinstance(x, dict)]
            if isinstance(obj, dict):
                # common patterns: {"items":[...]} or {"data":[...]}
                for k in ("items", "data", "records"):
                    if isinstance(obj.get(k), list):
                        return [x for x in obj[k] if isinstance(x, dict)]
                return [obj]
        except Exception:
            pass

    # Fallback: JSONL
    out: List[Dict[str, Any]] = []
    for i, line in enumerate(raw_text.splitlines(), start=1):
        t = line.strip()
        if not t:
            continue
        if t in {"[", "]"}:
            continue
        if t.endswith(","):
            t = t[:-1].rstrip()

        try:
            obj = json.loads(t)
        except Exception:
            # Safe fallback for python-like dict lines
            try:
                obj = ast.literal_eval(t)
            except Exception as e:
                snippet = t[:200]
                raise RuntimeError(
                    f"Failed to parse JSON at {path}:{i}\n"
                    f"Line snippet: {snippet}\n"
                    f"Original error: {e}"
                )
        if isinstance(obj, dict):
            out.append(obj)
    return out


def get_aoai_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=_env("AZURE_OPENAI_ENDPOINT", required=True),
        api_version=_env("AZURE_OPENAI_API_VERSION", "2024-06-01"),
        azure_ad_token_provider=get_aoai_token_provider(),
    )


def detect_embedding_dim(client: AzureOpenAI, deployment: str) -> int:
    """
    Auto-detect embedding size to prevent 1536 vs 1024 mismatch forever.
    """
    resp = client.embeddings.create(model=deployment, input="dimension probe")
    emb = resp.data[0].embedding
    return len(emb)


def embed_text(client: AzureOpenAI, deployment: str, text_value: str, retries: int = 5) -> List[float]:
    """
    Embedding with retries for transient failures.
    """
    last_err: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            resp = client.embeddings.create(model=deployment, input=text_value)
            return resp.data[0].embedding
        except NotFoundError as e:
            # Deployment name wrong OR not ready
            raise RuntimeError(
                f"Azure OpenAI embedding deployment not found.\n"
                f"Check AZURE_OPENAI_EMBEDDING_DEPLOYMENT in .env\n"
                f"Deployment: {deployment}\n"
                f"Error: {e}"
            )
        except (RateLimitError, APIError) as e:
            last_err = e
            time.sleep(min(2**attempt, 10))
        except Exception as e:
            last_err = e
            time.sleep(min(2**attempt, 10))
    raise RuntimeError(f"Embedding failed after retries: {last_err}")


def get_index_clients() -> Tuple[SearchIndexClient, SearchClient]:
    endpoint = _env("AZURE_SEARCH_ENDPOINT", required=True)
    index_name = _env("AZURE_SEARCH_INDEX_NAME", "meta_data_field_v3")
    cred = get_msi_credential()
    return (
        SearchIndexClient(endpoint=endpoint, credential=cred),
        SearchClient(endpoint=endpoint, index_name=index_name, credential=cred),
    )


def build_index(index_name: str, vector_dim: int) -> SearchIndex:
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
        profiles=[VectorSearchProfile(name="vprofile", algorithm_configuration_name="hnsw")],
    )

    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True, sortable=False),
        SimpleField(name="raw_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="doc_type", type=SearchFieldDataType.String, filterable=True),

        # Table fields
        SimpleField(name="schema_name", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="table_name", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="column_name", type=SearchFieldDataType.String, filterable=True),

        SearchableField(name="table_business_name", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SearchableField(name="table_business_description", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SearchableField(name="grain", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SearchableField(name="primary_keys", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SearchableField(name="default_filters", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SearchableField(name="notes", type=SearchFieldDataType.String, analyzer_name="en.lucene"),

        # Relationship fields
        SimpleField(name="from_schema", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="from_table", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="to_schema", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="to_table", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="join_type", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="join_keys", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SimpleField(name="cardinality", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="relationship_description", type=SearchFieldDataType.String, analyzer_name="en.lucene"),
        SimpleField(name="active", type=SearchFieldDataType.Boolean, filterable=True),

        # Main searchable content for RAG
        SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="en.lucene"),

        # Vector field
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=vector_dim,
            vector_search_profile_name="vprofile",
        ),
    ]

    return SearchIndex(name=index_name, fields=fields, vector_search=vector_search)


def index_schema_compatible(existing: SearchIndex, expected_dim: int) -> bool:
    """
    Ensure the index has our expected fields and vector dimension.
    If not, you MUST recreate to avoid "id cannot be changed" etc.
    """
    # key field must be id
    key_fields = [f for f in existing.fields if getattr(f, "key", False)]
    if not key_fields or key_fields[0].name != "id":
        return False

    # vector dim must match
    vec_fields = [f for f in existing.fields if f.name == "content_vector"]
    if not vec_fields:
        return False
    if getattr(vec_fields[0], "vector_search_dimensions", None) != expected_dim:
        return False

    # must contain critical fields used in $select
    required = {
        "raw_id", "doc_type", "schema_name", "table_name", "column_name",
        "from_schema", "from_table", "to_schema", "to_table", "join_keys",
        "content",
    }
    existing_names = {f.name for f in existing.fields}
    return required.issubset(existing_names)


def drop_legacy_v2_indexes(index_client: SearchIndexClient) -> None:
    """
    Drops known legacy indexes to prevent schema conflicts.
    """
    legacy = {
        "meta_data_table_v2",
        "meta_data_vector_v2",
        "meta_data_field_v2",
        "meta_data_table",
        "meta_data_vector",
        "meta_data_field",
    }
    for name in legacy:
        try:
            index_client.delete_index(name)
            print(f"✅ Dropped index: {name}")
        except Exception:
            pass


def normalize_table_doc(raw: Dict[str, Any]) -> Dict[str, Any]:
    schema = raw.get("schema_name") or ""
    table = raw.get("table_name") or ""
    raw_id = raw.get("id") or f"table.{schema}.{table}"
    content = raw.get("content") or build_table_content(raw)

    doc = {
        "id": safe_doc_id(str(raw_id)),
        "raw_id": str(raw_id),
        "doc_type": "table",
        "schema_name": schema or None,
        "table_name": table or None,
        "column_name": raw.get("column_name") or None,

        "table_business_name": raw.get("table_business_name") or None,
        "table_business_description": raw.get("table_business_description") or None,
        "grain": raw.get("grain") or None,
        "primary_keys": raw.get("primary_keys") or None,
        "default_filters": raw.get("default_filters") or None,
        "notes": raw.get("notes") or None,

        # relationship fields kept empty
        "from_schema": None, "from_table": None, "to_schema": None, "to_table": None,
        "join_type": None, "join_keys": None, "cardinality": None,
        "relationship_description": None, "active": None,

        "content": content,
    }
    return doc


def normalize_relationship_doc(raw: Dict[str, Any]) -> Dict[str, Any]:
    raw_id = raw.get("id") or "relationship.unknown"
    content = raw.get("content") or build_rel_content(raw)

    doc = {
        "id": safe_doc_id(str(raw_id)),
        "raw_id": str(raw_id),
        "doc_type": "relationship",

        # table fields empty
        "schema_name": None, "table_name": None, "column_name": None,
        "table_business_name": None, "table_business_description": None,
        "grain": None, "primary_keys": None, "default_filters": None, "notes": None,

        # relationship fields
        "from_schema": raw.get("from_schema") or None,
        "from_table": raw.get("from_table") or None,
        "to_schema": raw.get("to_schema") or None,
        "to_table": raw.get("to_table") or None,
        "join_type": raw.get("join_type") or None,
        "join_keys": raw.get("join_keys") or None,
        "cardinality": raw.get("cardinality") or None,
        "relationship_description": raw.get("relationship_description") or None,
        "active": bool(raw.get("active")) if raw.get("active") is not None else None,

        "content": content,
    }
    return doc


def main() -> None:
    index_client, search_client = get_index_clients()

    index_name = _env("AZURE_SEARCH_INDEX_NAME", "meta_data_field_v3")
    table_path = _env("TABLE_DOCS_PATH", required=True)
    rel_path = _env("REL_DOCS_PATH", required=True)

    drop_v2 = _env_bool("DROP_LEGACY_V2", True)
    force_recreate = _env_bool("FORCE_RECREATE_INDEX", False)

    aoai = get_aoai_client()
    emb_deployment = _env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", required=True)

    vector_dim = detect_embedding_dim(aoai, emb_deployment)
    print(f"✅ Detected embedding dimension: {vector_dim}")

    if drop_v2:
        drop_legacy_v2_indexes(index_client)

    # Ensure index exists and compatible
    try:
        existing = index_client.get_index(index_name)
        if not index_schema_compatible(existing, vector_dim):
            if not force_recreate:
                raise RuntimeError(
                    f"Index '{index_name}' exists but schema/dim is not compatible.\n"
                    f"Set FORCE_RECREATE_INDEX=true to recreate safely."
                )
            print(f"⚠️ Recreating incompatible index: {index_name}")
            index_client.delete_index(index_name)
            index_client.create_index(build_index(index_name, vector_dim))
        else:
            print(f"✅ Index OK: {index_name}")
    except ResourceNotFoundError:
        print(f"🆕 Creating index: {index_name}")
        index_client.create_index(build_index(index_name, vector_dim))

    # Load docs
    print(f"📄 Reading tables: {table_path}")
    table_raw = load_records(table_path)

    print(f"📄 Reading relationships: {rel_path}")
    rel_raw = load_records(rel_path)

    docs: List[Dict[str, Any]] = []
    for r in table_raw:
        docs.append(normalize_table_doc(r))
    for r in rel_raw:
        docs.append(normalize_relationship_doc(r))

    print(f"✅ Loaded {len(docs)} metadata records")

    # Embed
    print("🧠 Creating embeddings...")
    for i, d in enumerate(docs, start=1):
        d["content_vector"] = embed_text(aoai, emb_deployment, (d.get("content") or "")[:8000])
        if i % 200 == 0:
            print(f"  embedded {i}/{len(docs)}")

    # Upload
    batch_size = 500
    print("⬆️ Uploading documents...")
    for start in range(0, len(docs), batch_size):
        chunk = docs[start:start + batch_size]
        try:
            res = search_client.upload_documents(chunk)
            failed = [r for r in res if not r.succeeded]
            if failed:
                first = failed[0]
                raise RuntimeError(f"Upload failed for key={first.key}. Error={first.error_message}")
            print(f"  uploaded {min(start+batch_size, len(docs))}/{len(docs)}")
        except HttpResponseError as e:
            raise RuntimeError(f"Azure Search upload failed: {e}")

    print("✅ Done.")


if __name__ == "__main__":
    main()
