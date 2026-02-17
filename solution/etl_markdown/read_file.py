from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.models import VectorizedQuery

from embedding_utils import get_embedding, chat_completion

load_dotenv(override=True)

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"


# ----------------------------
# Azure Search clients
# ----------------------------
def _get_search_endpoint() -> str:
    # support either full endpoint or account name
    endpoint = os.getenv("SEARCH_ENDPOINT", "").strip()
    if endpoint:
        return endpoint
    acct = os.getenv("AISEARCH_ACCOUNT", "").strip() or os.getenv("AISEARCH_SERVICE", "").strip()
    if not acct:
        raise RuntimeError("Missing SEARCH_ENDPOINT or AISEARCH_ACCOUNT in .env")
    return f"https://{acct}.search.windows.net"


def _get_index_name() -> str:
    return (os.getenv("INDEX_NAME", "").strip() or "meta_data_field_v3")


def _get_credential():
    # Prefer user-assigned MSI if CLIENT_ID provided
    client_id = os.getenv("CLIENT_ID", "").strip()
    if client_id:
        return ManagedIdentityCredential(client_id=client_id)
    return DefaultAzureCredential(exclude_interactive_browser_credential=False)


def get_search_clients() -> Tuple[SearchClient, SearchIndexClient]:
    endpoint = _get_search_endpoint()
    index_name = _get_index_name()
    cred = _get_credential()
    search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=cred)
    index_client = SearchIndexClient(endpoint=endpoint, credential=cred)
    return search_client, index_client


def _get_index_field_names(index_client: SearchIndexClient, index_name: str) -> List[str]:
    idx = index_client.get_index(index_name)
    return [f.name for f in idx.fields]  # type: ignore[attr-defined]


def _safe_select_fields(existing: List[str], desired: List[str]) -> List[str]:
    s = set(existing)
    return [f for f in desired if f in s]


# ----------------------------
# Metadata retrieval + formatting
# ----------------------------
def retrieve_metadata_markdown(
    question: str,
    top_k: int = 25,
    search_client: Optional[SearchClient] = None,
    index_client: Optional[SearchIndexClient] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Runs a hybrid search (keyword + vector) against the metadata index and returns:
    - markdown schema context
    - raw hits (dicts)
    """
    if not search_client or not index_client:
        search_client, index_client = get_search_clients()

    index_name = _get_index_name()
    existing_fields = _get_index_field_names(index_client, index_name)

    # Pick fields that exist (NO hardcoding)
    desired = [
        "schema_name",
        "table_name",
        "column_name",
        "business_name",
        "business_description",
        "data_type",
        "allowed_values",
        "notes",
        "pii",
        "pci",
        "is_key",
        "is_filter_hint",
        "security_classification_candidate",
    ]
    select_fields = _safe_select_fields(existing_fields, desired)

    # Vector query (field name may differ: support common names)
    vector_field_candidates = ["content_vector", "description_vector", "vector", "embedding"]
    vector_field = next((f for f in vector_field_candidates if f in existing_fields), None)
    if not vector_field:
        raise RuntimeError(
            f"No vector field found in index '{index_name}'. "
            f"Tried {vector_field_candidates}. Existing fields: {existing_fields}"
        )

    q_vec = get_embedding(question)
    vq = VectorizedQuery(vector=q_vec, k_nearest_neighbors=top_k, fields=vector_field)

    results = search_client.search(
        search_text=question,                 # hybrid
        vector_queries=[vq],
        top=top_k,
        select=select_fields if select_fields else None,
    )

    hits: List[Dict[str, Any]] = []
    for r in results:
        # r behaves like dict
        hits.append(dict(r))

    # If nothing found, return empty context
    if not hits:
        return "", []

    # Group by schema.table
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for h in hits:
        schema = (h.get("schema_name") or "").strip()
        table = (h.get("table_name") or "").strip()
        key = f"{schema}.{table}".strip(".") or "UNKNOWN_TABLE"
        grouped.setdefault(key, []).append(h)

    lines: List[str] = []
    lines.append("## Retrieved Metadata (Top Matches)")
    lines.append("Use ONLY the following tables/columns. Do NOT invent names.\n")

    # Build concise but rich schema context
    for table_key, rows in list(grouped.items())[:12]:
        lines.append(f"### Table: `{table_key}`")
        # Prefer table-level business description if present in any row
        table_desc = ""
        for rr in rows:
            bd = (rr.get("business_description") or "").strip()
            if bd:
                table_desc = bd
                break
        if table_desc:
            lines.append(f"- Business description: {table_desc}")

        # Columns
        lines.append("- Columns:")
        seen_cols = set()
        for rr in rows:
            col = (rr.get("column_name") or "").strip()
            if not col or col in seen_cols:
                continue
            seen_cols.add(col)
            dtype = (rr.get("data_type") or "").strip()
            bn = (rr.get("business_name") or "").strip()
            pii = rr.get("pii")
            pci = rr.get("pci")
            is_key = rr.get("is_key")
            hints = []
            if pii is True:
                hints.append("PII")
            if pci is True:
                hints.append("PCI")
            if is_key is True:
                hints.append("KEY")
            hint_txt = f" [{' / '.join(hints)}]" if hints else ""
            label = f"`{col}`"
            meta = " · ".join([x for x in [dtype, bn] if x])
            if meta:
                lines.append(f"  - {label}{hint_txt} — {meta}")
            else:
                lines.append(f"  - {label}{hint_txt}")

        lines.append("")  # blank line

    return "\n".join(lines).strip(), hits


# ----------------------------
# LLM: SQL or Clarify (STRICT JSON)
# ----------------------------
def generate_sql_or_clarify(question: str, engine_dialect: str = "sqlite") -> Dict[str, Any]:
    """
    Returns:
      {"action":"sql","sql":"..."} OR {"action":"clarify","question":"..."}
    """
    schema_md, hits = retrieve_metadata_markdown(question)

    # If retrieval is weak, force clarification instead of hallucinating
    if not schema_md or len(hits) < 3:
        return {
            "action": "clarify",
            "question": (
                "I couldn’t find enough matching metadata in Azure AI Search. "
                "Which schema/table should I use (or what business area is this about)?"
            ),
        }

    prompt = f"""
You are a data analyst who generates SQL for the user's question.

You MUST return STRICT JSON ONLY (no markdown, no code fences).
Choose exactly one action:

1) If you have enough info to write correct SQL using ONLY provided tables/columns:
   {{"action":"sql","sql":"<SQL here>"}}

2) If the question is ambiguous or missing table/schema details:
   {{"action":"clarify","question":"<ask 1-2 short clarifying questions>"}}

Rules:
- SQL dialect: {engine_dialect}
- Use ONLY tables and columns that appear in the metadata below.
- Do NOT invent table/column names.
- If you need a table name, ask to clarify (action=clarify).
- Return JSON only.

METADATA:
{schema_md}

USER QUESTION:
{question}
""".strip()

    raw = chat_completion(prompt, temperature=0.0)

    # Robust JSON parse
    obj: Dict[str, Any]
    try:
        obj = json.loads(raw)
    except Exception:
        # fallback: treat as sql if it looks like sql; else clarification
        low = raw.strip().lower()
        if low.startswith("select") or low.startswith("with"):
            obj = {"action": "sql", "sql": raw.strip()}
        else:
            obj = {"action": "clarify", "question": raw.strip() or "Can you clarify your request?"}

    action = (obj.get("action") or "").strip().lower()
    if action not in ("sql", "clarify"):
        # defensive default
        return {"action": "clarify", "question": "Can you clarify what you need (which table/schema)?", "raw": raw}

    if action == "sql":
        sql = (obj.get("sql") or "").strip()
        # remove accidental fences
        sql = sql.strip("`").strip()
        if sql.lower().startswith("sql"):
            sql = sql[3:].strip()
        return {"action": "sql", "sql": sql, "schema_md": schema_md}

    q = (obj.get("question") or "").strip()
    return {"action": "clarify", "question": q or "Can you clarify your request?", "schema_md": schema_md}


def ask_llm_to_fix_sql(
    question: str,
    prev_sql: str,
    error_msg: str,
    engine_dialect: str = "sqlite",
) -> Dict[str, Any]:
    """
    Same strict JSON contract as generate_sql_or_clarify.
    """
    schema_md, _ = retrieve_metadata_markdown(question)

    prompt = f"""
You generated SQL that failed execution.

Return STRICT JSON ONLY (no markdown, no code fences):
- If you can fix it: {{"action":"sql","sql":"<corrected SQL>"}}
- If you need clarification: {{"action":"clarify","question":"<ask short clarifying question(s)>"}}

Rules:
- Dialect: {engine_dialect}
- Use ONLY tables/columns from METADATA.
- Do NOT invent names.

USER QUESTION:
{question}

FAILED SQL:
{prev_sql}

ERROR:
{error_msg}

METADATA:
{schema_md}
""".strip()

    raw = chat_completion(prompt, temperature=0.0)

    try:
        obj = json.loads(raw)
    except Exception:
        low = raw.strip().lower()
        if low.startswith("select") or low.startswith("with"):
            obj = {"action": "sql", "sql": raw.strip()}
        else:
            obj = {"action": "clarify", "question": raw.strip()}

    action = (obj.get("action") or "").strip().lower()
    if action == "sql":
        return {"action": "sql", "sql": (obj.get("sql") or "").strip()}
    return {"action": "clarify", "question": (obj.get("question") or "Can you clarify?").strip()}
