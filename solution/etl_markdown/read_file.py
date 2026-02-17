from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from azure.identity import ManagedIdentityCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import AzureOpenAI


DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

COG_SCOPE = "https://cognitiveservices.azure.com/.default"


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def get_msi_credential() -> ManagedIdentityCredential:
    """
    MSI-only credential:
    - no DefaultAzureCredential
    - no az login
    - no interactive browser prompt
    """
    client_id = os.getenv("AZURE_MSI_CLIENT_ID", "").strip() or None
    return ManagedIdentityCredential(client_id=client_id)


def get_search_client() -> SearchClient:
    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "").strip()
    index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "meta_data_field_v3").strip()
    if not endpoint:
        raise RuntimeError("AZURE_SEARCH_ENDPOINT is missing in .env")
    cred = get_msi_credential()
    return SearchClient(endpoint=endpoint, index_name=index_name, credential=cred)


def get_aoai_client() -> AzureOpenAI:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21").strip()
    if not endpoint:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT is missing in .env")

    cred = get_msi_credential()
    token_provider = get_bearer_token_provider(cred, COG_SCOPE)

    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_version=api_version,
        azure_ad_token_provider=token_provider,
    )


def get_chat_deployment() -> str:
    dep = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "").strip()
    if not dep:
        raise RuntimeError("AZURE_OPENAI_CHAT_DEPLOYMENT is missing in .env")
    return dep


def get_embed_deployment() -> str:
    dep = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT", "").strip()
    if not dep:
        raise RuntimeError("AZURE_OPENAI_EMBED_DEPLOYMENT is missing in .env")
    return dep


def embed_text(text: str) -> List[float]:
    """
    Returns embedding vector. MSI-only.
    If the deployment is wrong, raises with a clear message.
    """
    client = get_aoai_client()
    dep = get_embed_deployment()
    try:
        resp = client.embeddings.create(model=dep, input=text)
        return list(resp.data[0].embedding)
    except Exception as e:
        raise RuntimeError(
            "Embedding call failed. Check AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_EMBED_DEPLOYMENT.\n"
            f"Original error: {e}"
        )


def _safe_json_loads(s: str) -> Dict[str, Any]:
    """
    LLM sometimes returns JSON wrapped in text. Extract the first {...} block.
    """
    s = s.strip()
    if s.startswith("{") and s.endswith("}"):
        return json.loads(s)

    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if not m:
        raise ValueError(f"LLM did not return JSON. Got: {s[:300]}")
    return json.loads(m.group(0))


def _dialect_name(engine) -> str:
    return getattr(getattr(engine, "dialect", None), "name", "").lower()


def strip_schema_prefixes_for_sqlite(sql: str, known_schemas: Optional[List[str]] = None) -> str:
    """
    SQLite does not support schema.table unless schema is an attached database.
    Remove schema qualifiers only in FROM/JOIN targets.
    """
    if not sql:
        return sql
    schemas = {s.lower() for s in (known_schemas or []) if s}
    # If we don't know schemas, still remove common patterns like rrdw_dlv.<table> in FROM/JOIN.
    common_like = {"dbo", "public", "rrdw_dlv", "rrdw", "amcb", "default"}
    schemas = schemas.union(common_like)

    def repl(m: re.Match) -> str:
        kw = m.group(1)
        sch = m.group(2)
        tbl = m.group(3)
        if sch.lower() in schemas:
            return f"{kw} {tbl}"
        return m.group(0)

    pattern = re.compile(r"\b(FROM|JOIN)\s+([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)\b", re.IGNORECASE)
    return pattern.sub(repl, sql)


@dataclass
class SearchHit:
    doc_type: str
    schema_name: str
    table_name: str
    field_name: str
    content: str
    from_table: str
    to_table: str
    join_keys: str
    relationship_description: str


def _hit_from_doc(doc: Dict[str, Any]) -> SearchHit:
    return SearchHit(
        doc_type=str(doc.get("doc_type", "") or ""),
        schema_name=str(doc.get("schema_name", "") or ""),
        table_name=str(doc.get("table_name", "") or ""),
        field_name=str(doc.get("field_name", "") or ""),
        content=str(doc.get("content", "") or ""),
        from_table=str(doc.get("from_table", "") or ""),
        to_table=str(doc.get("to_table", "") or ""),
        join_keys=str(doc.get("join_keys", "") or ""),
        relationship_description=str(doc.get("relationship_description", "") or ""),
    )


def search_metadata(question: str, search_client: SearchClient, top_k: int = 8) -> Tuple[List[SearchHit], List[str]]:
    """
    Hybrid retrieval: text search + vector search.
    If embeddings fail, falls back to text-only.
    """
    logs: List[str] = []
    logs.append(f"[{_now()}] Searching Azure AI Search metadata...")

    select_fields = [
        "doc_type",
        "schema_name",
        "table_name",
        "field_name",
        "content",
        "from_table",
        "to_table",
        "join_keys",
        "relationship_description",
    ]

    vector_queries = None
    try:
        qvec = embed_text(question)
        vector_queries = [
            VectorizedQuery(vector=qvec, k_nearest_neighbors=top_k, fields="content_vector")
        ]
        logs.append(f"[{_now()}] Vector search enabled (dim={len(qvec)}).")
    except Exception as e:
        logs.append(f"[{_now()}] Vector search disabled (embedding failed): {e}")

    results = search_client.search(
        search_text=question,
        top=top_k,
        select=select_fields,
        vector_queries=vector_queries,
    )

    hits: List[SearchHit] = []
    for r in results:
        hits.append(_hit_from_doc(dict(r)))

    logs.append(f"[{_now()}] Retrieved {len(hits)} metadata hits.")
    return hits, logs


def _format_context(hits: List[SearchHit], dialect: str) -> Tuple[str, List[str], List[str]]:
    """
    Build a compact context for the LLM.
    Also returns: known_schemas, candidate_tables
    """
    known_schemas = sorted({h.schema_name for h in hits if h.schema_name})
    candidate_tables = sorted({h.table_name for h in hits if h.table_name})

    # Separate by type for readability
    tables = [h for h in hits if h.doc_type == "table"]
    fields = [h for h in hits if h.doc_type == "field"]
    rels = [h for h in hits if h.doc_type == "relationship"]

    def clip(s: str, n: int = 900) -> str:
        s = (s or "").strip()
        return s if len(s) <= n else s[:n] + "..."

    parts: List[str] = []
    parts.append(f"SQL_DIALECT={dialect}\n")

    parts.append("## TABLE DOCS (high level)\n")
    for h in tables[:12]:
        parts.append(f"- schema={h.schema_name} table={h.table_name}\n{clip(h.content)}\n")

    parts.append("## FIELD DOCS (columns)\n")
    # Important: columns are the truth source for what exists
    for h in fields[:60]:
        parts.append(f"- table={h.table_name} column={h.field_name}\n{clip(h.content, 350)}\n")

    parts.append("## RELATIONSHIP DOCS (joins)\n")
    for h in rels[:30]:
        parts.append(
            f"- {h.from_table} -> {h.to_table} | keys: {h.join_keys}\n{clip(h.relationship_description, 350)}\n"
        )

    return "\n".join(parts), known_schemas, candidate_tables


def ask_question(question: str, search_client: SearchClient, engine) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """
    Returns:
      - llm_json: {"type":"sql","sql":"..."} OR {"type":"clarification","questions":[...]}
      - logs
      - known_schemas (for sqlite stripping)
    """
    dialect = _dialect_name(engine)
    hits, logs = search_metadata(question, search_client, top_k=10)

    # If we got table hits but not enough field hits, we do a second pass to fetch more fields for those tables
    candidate_tables = sorted({h.table_name for h in hits if h.table_name})
    if candidate_tables:
        # try to fetch more field docs for these tables
        filter_expr = " or ".join([f"(doc_type eq 'field' and table_name eq '{t}')" for t in candidate_tables[:5]])
        if filter_expr:
            try:
                more = search_client.search(
                    search_text="*",
                    top=80,
                    filter=filter_expr,
                    select=["doc_type", "schema_name", "table_name", "field_name", "content"],
                )
                for r in more:
                    hits.append(_hit_from_doc(dict(r)))
                logs.append(f"[{_now()}] Expanded field docs for candidate tables.")
            except Exception as e:
                logs.append(f"[{_now()}] Field expansion failed (non-fatal): {e}")

    context, known_schemas, _ = _format_context(hits, dialect)

    # Strong rules to stop hallucinations (RRDW_AS_OF_DATE problem)
    system = (
        "You are a production Text-to-SQL assistant.\n"
        "Return STRICT JSON only (no markdown, no extra text).\n"
        "Allowed outputs:\n"
        "1) {\"type\":\"sql\",\"sql\":\"...\",\"notes\":\"...\"}\n"
        "2) {\"type\":\"clarification\",\"questions\":[\"...\",\"...\"],\"notes\":\"...\"}\n\n"
        "Rules:\n"
        "- Use ONLY columns that appear in FIELD DOCS.\n"
        "- If the question needs a date column but none exists in FIELD DOCS, return type=clarification.\n"
        "- Prefer joins ONLY when RELATIONSHIP DOCS provide join keys.\n"
        "- If SQL_DIALECT=sqlite: DO NOT prefix tables with schema (no schema.table).\n"
        "- Keep SQL minimal and executable.\n"
    )

    user = (
        f"User question:\n{question}\n\n"
        f"Metadata context:\n{context}\n\n"
        "Now produce the JSON response."
    )

    client = get_aoai_client()
    chat_dep = get_chat_deployment()

    logs.append(f"[{_now()}] Sending request to LLM (chat deployment={chat_dep}).")
    resp = client.chat.completions.create(
        model=chat_dep,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.0,
    )
    raw = resp.choices[0].message.content or ""
    logs.append(f"[{_now()}] LLM responded.")

    try:
        data = _safe_json_loads(raw)
    except Exception as e:
        logs.append(f"[{_now()}] JSON parse failed: {e}")
        data = {
            "type": "clarification",
            "questions": [
                "I could not parse the model output as JSON. Can you re-run after verifying the chat deployment returns JSON?"
            ],
            "notes": raw[:500],
        }

    # Post-process for sqlite schema stripping
    if data.get("type") == "sql" and isinstance(data.get("sql"), str) and dialect == "sqlite":
        data["sql"] = strip_schema_prefixes_for_sqlite(data["sql"], known_schemas=known_schemas)

    return data, logs, known_schemas


def ask_llm_to_fix_sql(
    question: str,
    prev_sql: str,
    error_msg: str,
    search_client: SearchClient,
    engine,
    known_schemas: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Fixer also returns JSON. Enforces sqlite no-schema rule again.
    """
    logs: List[str] = []
    dialect = _dialect_name(engine)

    # Bring back some metadata again for grounding
    hits, s_logs = search_metadata(question, search_client, top_k=8)
    logs.extend(s_logs)
    context, known_schemas2, _ = _format_context(hits, dialect)
    known = known_schemas or known_schemas2

    system = (
        "You are a SQL expert. Return STRICT JSON only.\n"
        "Output:\n"
        " - {\"type\":\"sql\",\"sql\":\"...\",\"notes\":\"...\"}\n"
        " - OR {\"type\":\"clarification\",\"questions\":[...],\"notes\":\"...\"}\n\n"
        "Rules:\n"
        "- Fix the SQL to resolve the error.\n"
        "- Use ONLY columns present in FIELD DOCS.\n"
        "- If the error indicates missing table/column, ask clarification instead of guessing.\n"
        "- If SQL_DIALECT=sqlite: DO NOT use schema.table.\n"
    )

    user = (
        f"User question:\n{question}\n\n"
        f"Previous SQL:\n{prev_sql}\n\n"
        f"Error message:\n{error_msg}\n\n"
        f"Metadata context:\n{context}\n\n"
        "Return JSON now."
    )

    client = get_aoai_client()
    chat_dep = get_chat_deployment()
    logs.append(f"[{_now()}] Sending SQL-fix request to LLM.")
    resp = client.chat.completions.create(
        model=chat_dep,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0,
    )
    raw = resp.choices[0].message.content or ""
    logs.append(f"[{_now()}] LLM returned SQL-fix response.")

    data = _safe_json_loads(raw)

    if data.get("type") == "sql" and isinstance(data.get("sql"), str) and dialect == "sqlite":
        data["sql"] = strip_schema_prefixes_for_sqlite(data["sql"], known_schemas=known)

    return data, logs
