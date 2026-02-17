from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from azure.identity import ManagedIdentityCredential
from azure.core.credentials import TokenCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.models import VectorizedQuery

from openai import AzureOpenAI

load_dotenv()


# ----------------------------
# Credentials (MSI only)
# ----------------------------
def get_msi_credential() -> ManagedIdentityCredential:
    client_id = os.getenv("AZURE_CLIENT_ID", "").strip() or None
    # ManagedIdentityCredential never opens a browser.
    return ManagedIdentityCredential(client_id=client_id)


def get_aoai_client(credential: TokenCredential) -> AzureOpenAI:
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21").strip()
    if not endpoint:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT is missing in .env")

    # Token provider for OpenAI SDK
    def _token_provider() -> str:
        tok = credential.get_token("https://cognitiveservices.azure.com/.default")
        return tok.token

    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_version=api_version,
        azure_ad_token_provider=_token_provider,
    )


def get_search_clients(credential: TokenCredential) -> Tuple[SearchIndexClient, SearchClient]:
    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "").strip()
    index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "meta_data_v3").strip()
    if not endpoint:
        raise RuntimeError("AZURE_SEARCH_ENDPOINT is missing in .env")

    index_client = SearchIndexClient(endpoint=endpoint, credential=credential)
    search_client = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)
    return index_client, search_client


# ----------------------------
# Retrieval + SQL generation
# ----------------------------
@dataclass
class Hit:
    id: str
    score: float
    doc_type: str
    schema_name: Optional[str]
    table_name: Optional[str]
    column_name: Optional[str]
    content: str


def embed_text(
    aoai: AzureOpenAI,
    text: str,
    deployment: str,
    desired_dim: Optional[int] = None,
) -> List[float]:
    if not text:
        text = " "
    kwargs: Dict[str, Any] = {"model": deployment, "input": text}
    # Only pass dimensions if provided (some models support it)
    if desired_dim is not None:
        kwargs["dimensions"] = int(desired_dim)
    resp = aoai.embeddings.create(**kwargs)
    return list(resp.data[0].embedding)


def search_metadata(
    aoai: AzureOpenAI,
    search_client: SearchClient,
    question: str,
    vector_dim: Optional[int],
    top_k: int = 12,
) -> List[Hit]:
    q = (question or "").strip()
    if not q:
        return []

    emb_deploy = os.getenv("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT", "").strip()
    if not emb_deploy:
        raise RuntimeError("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT is missing in .env")

    vec = embed_text(aoai, q, emb_deploy, desired_dim=vector_dim)
    vq = VectorizedQuery(vector=vec, k_nearest_neighbors=top_k, fields="content_vector")

    results = search_client.search(
        search_text=q,
        vector_queries=[vq],
        top=top_k,
        select=["id","doc_type","schema_name","table_name","column_name","content"],
    )

    hits: List[Hit] = []
    for r in results:
        doc = dict(r)
        hits.append(
            Hit(
                id=str(doc.get("id","")),
                score=float(doc.get("@search.score", 0.0)),
                doc_type=str(doc.get("doc_type","")),
                schema_name=doc.get("schema_name"),
                table_name=doc.get("table_name"),
                column_name=doc.get("column_name"),
                content=str(doc.get("content","")),
            )
        )
    return hits


def _dialect_name(engine) -> str:
    try:
        return (engine.dialect.name or "").lower()
    except Exception:
        return ""


def _extract_tables_from_sql(sql: str) -> List[str]:
    # Very small parser: FROM <x> and JOIN <x> (ignores subqueries)
    s = (sql or "")
    pat = re.compile(r"\b(from|join)\s+([A-Za-z_][\w\.]*)(?:\s+as)?\s*[A-Za-z_][\w]*?", re.I)
    out: List[str] = []
    for m in pat.finditer(s):
        t = m.group(2).strip()
        # remove quoting/brackets if any
        t = t.strip('"`[]')
        out.append(t)
    return list(dict.fromkeys(out))


def strip_schema_for_sqlite(sql: str, known_schemas: List[str], sqlite_tables: List[str]) -> str:
    # Replace schema.table -> table only when schema in known_schemas AND table exists in sqlite.
    if not sql:
        return sql
    schema_set = set([s.lower() for s in known_schemas if s])
    table_set = set([t.lower() for t in sqlite_tables if t])

    def repl(m):
        sch = m.group(1)
        tbl = m.group(2)
        if sch.lower() in schema_set and tbl.lower() in table_set:
            return tbl
        return m.group(0)

    return re.sub(r"\b([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)\b", repl, sql)


def build_context(
    hits: List[Hit],
    table_schemas: Dict[str, List[str]],
    dialect: str,
    max_items: int = 10,
) -> Tuple[str, List[str]]:
    """
    Returns (context_text, known_schemas).
    Context includes only information we can defend:
    - tables/columns from DB (table_schemas)
    - relationship text from hits
    - field/table descriptions from hits
    """
    # Known schemas from metadata hits (used only to strip for sqlite)
    known_schemas = sorted({(h.schema_name or "").strip() for h in hits if (h.schema_name or "").strip()})
    sqlite_tables = sorted(table_schemas.keys())

    # Build a compact list of relevant tables from hits, but validated against DB tables for sqlite
    relevant_tables: List[str] = []
    for h in hits:
        if h.table_name:
            relevant_tables.append(h.table_name)
    relevant_tables = list(dict.fromkeys([t for t in relevant_tables if t]))

    # For sqlite: only allow tables that truly exist
    if dialect == "sqlite":
        relevant_tables = [t for t in relevant_tables if t in table_schemas]

    # Include columns only for relevant tables and only those that exist in DB schema
    table_blocks: List[str] = []
    for t in relevant_tables[:max_items]:
        cols = table_schemas.get(t, [])
        if cols:
            table_blocks.append(f"- {t}: columns = {', '.join(cols[:80])}")

    # Relationship snippets
    rel_snips: List[str] = []
    for h in hits:
        if h.doc_type == "relationship" and h.content:
            rel_snips.append(f"- {h.content.strip()[:500]}")

    # Descriptions (best effort)
    desc_snips: List[str] = []
    for h in hits:
        if h.doc_type in ("field","table") and h.content:
            desc_snips.append(f"- {h.content.strip()[:500]}")

    dialect_note = (
        "SQLite rules: DO NOT use schema prefixes. Use ONLY table names like `v_dlv_dep_tran`."
        if dialect == "sqlite"
        else "Use full table identifiers as needed by the target database."
    )

    context = "\n".join([
        f"Database dialect: {dialect}",
        dialect_note,
        "\nAvailable tables in the connected DB:",
        "- " + ", ".join(sqlite_tables[:200]) if sqlite_tables else "- (unknown)",
        "\nRelevant tables & columns (from DB schema):",
        "\n".join(table_blocks) if table_blocks else "- (no relevant tables confirmed)",
        "\nRelationships (from metadata):",
        "\n".join(rel_snips[:max_items]) if rel_snips else "- (none found)",
        "\nDescriptions (from metadata):",
        "\n".join(desc_snips[:max_items]) if desc_snips else "- (none found)",
    ])
    return context, known_schemas


def _clean_code_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\n?", "", t).strip()
        t = t.rstrip("`").strip()
    return t.strip()


def generate_sql_or_clarification(
    aoai: AzureOpenAI,
    question: str,
    context: str,
) -> Dict[str, Any]:
    chat_deploy = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "").strip()
    if not chat_deploy:
        raise RuntimeError("AZURE_OPENAI_CHAT_DEPLOYMENT is missing in .env")

    system = (
        "You are a careful SQL assistant.
"
        "Rules:
"
        "1) Use ONLY the tables and columns that appear in the provided context under 'Relevant tables & columns'.
"
        "2) If required info is missing (table not confirmed, column not listed, filters unclear), ask clarifying questions.
"
        "3) Return STRICT JSON with one of these shapes:
"
        "   A) {"type":"sql","sql":"..."}
"
        "   B) {"type":"clarification","questions":["...", "..."]}
"
        "4) Do NOT include markdown. Do NOT include extra keys.
"
    )

    user = f"QUESTION:\n{question}\n\nCONTEXT:\n{context}\n"
    resp = aoai.chat.completions.create(
        model=chat_deploy,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
    )
    raw = resp.choices[0].message.content or ""
    raw = _clean_code_fence(raw)

    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and obj.get("type") in ("sql","clarification"):
            return obj
    except Exception:
        pass

    # Fallback: treat as clarification
    return {
        "type": "clarification",
        "questions": [
            "I couldn't parse a valid JSON response. Please rephrase your request and specify the target table(s)."
        ],
    }


def fix_sql_on_error(
    aoai: AzureOpenAI,
    question: str,
    prev_sql: str,
    error_msg: str,
    context: str,
) -> Dict[str, Any]:
    chat_deploy = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "").strip()
    if not chat_deploy:
        raise RuntimeError("AZURE_OPENAI_CHAT_DEPLOYMENT is missing in .env")

    system = (
        "You are a careful SQL assistant.
"
        "Rules:
"
        "1) Use ONLY the tables and columns in the provided context under 'Relevant tables & columns'.
"
        "2) Fix the SQL to resolve the error.
"
        "3) If you cannot fix without new info, ask clarifying questions.
"
        "4) Return STRICT JSON:
"
        "   A) {"type":"sql","sql":"..."}
"
        "   B) {"type":"clarification","questions":["..."]}
"
    )

    user = (
        f"QUESTION:\n{question}\n\n"
        f"PREVIOUS_SQL:\n{prev_sql}\n\n"
        f"ERROR:\n{error_msg}\n\n"
        f"CONTEXT:\n{context}\n"
    )

    resp = aoai.chat.completions.create(
        model=chat_deploy,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
    )
    raw = _clean_code_fence(resp.choices[0].message.content or "")
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and obj.get("type") in ("sql","clarification"):
            return obj
    except Exception:
        pass
    return {"type": "clarification", "questions": ["Please clarify your request (target tables/filters)."]}


def validate_sql_against_db(sql: str, table_schemas: Dict[str, List[str]], dialect: str) -> Optional[str]:
    """
    Returns an error string if SQL references tables that do not exist in the connected DB (sqlite).
    """
    if dialect != "sqlite":
        return None
    used = _extract_tables_from_sql(sql)
    # Used items might still include schema.table; for sqlite validate table only
    missing: List[str] = []
    for t in used:
        if "." in t:
            t2 = t.split(".")[-1]
        else:
            t2 = t
        if t2 not in table_schemas:
            missing.append(t2)
    if missing:
        available = ", ".join(sorted(list(table_schemas.keys()))[:50])
        return f"Missing table(s) in sqlite DB: {', '.join(missing)}. Available tables include: {available}"
    return None
