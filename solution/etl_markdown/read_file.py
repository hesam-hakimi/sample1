# ai_utils.py
from __future__ import annotations

import os
import json
import re
from typing import Any, Dict, List, Tuple, Optional

from azure.search.documents import SearchClient
from azure.core.exceptions import HttpResponseError

from openai import AzureOpenAI
from openai import NotFoundError, RateLimitError, APIError

from auth_utils import get_msi_credential, get_aoai_token_provider

try:
    from azure.search.documents.models import VectorizedQuery  # type: ignore
except Exception:  # pragma: no cover
    VectorizedQuery = None


def _env(name: str, default: str = "", required: bool = False) -> str:
    v = (os.getenv(name) or default).strip()
    if required and not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def _env_int(name: str, default: int) -> int:
    v = (os.getenv(name) or "").strip()
    return int(v) if v else default


def setup_azure_search() -> SearchClient:
    return SearchClient(
        endpoint=_env("AZURE_SEARCH_ENDPOINT", required=True),
        index_name=_env("AZURE_SEARCH_INDEX_NAME", "meta_data_field_v3"),
        credential=get_msi_credential(),
    )


def get_aoai_client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=_env("AZURE_OPENAI_ENDPOINT", required=True),
        api_version=_env("AZURE_OPENAI_API_VERSION", "2024-06-01"),
        azure_ad_token_provider=get_aoai_token_provider(),
    )


def chat_deployment() -> str:
    return _env("AZURE_OPENAI_CHAT_DEPLOYMENT", required=True)


def emb_deployment() -> str:
    return _env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", required=True)


def embed_query(client: AzureOpenAI, text_value: str) -> List[float]:
    resp = client.embeddings.create(model=emb_deployment(), input=text_value)
    return resp.data[0].embedding


def search_metadata(search_client: SearchClient, aoai: AzureOpenAI, question: str, top_k: int = 8) -> List[Dict[str, Any]]:
    """
    Hybrid search (keyword + vector) if SDK supports vector_queries.
    """
    select_fields = [
        "doc_type",
        "schema_name", "table_name", "column_name",
        "table_business_name", "table_business_description",
        "from_schema", "from_table", "to_schema", "to_table",
        "join_type", "join_keys", "cardinality",
        "relationship_description",
        "content",
    ]

    try:
        if VectorizedQuery is not None:
            qvec = embed_query(aoai, question)
            vq = VectorizedQuery(vector=qvec, k_nearest_neighbors=top_k, fields="content_vector")
            results = search_client.search(
                search_text=question,
                vector_queries=[vq],
                top=top_k,
                select=select_fields,
            )
        else:
            results = search_client.search(
                search_text=question,
                top=top_k,
                select=select_fields,
            )
        out = []
        for r in results:
            out.append(dict(r))
        return out
    except HttpResponseError as e:
        raise RuntimeError(f"Azure AI Search query failed: {e}")


def build_context(docs: List[Dict[str, Any]]) -> str:
    """
    Compress docs into a context block the LLM can reliably use.
    """
    tables = [d for d in docs if d.get("doc_type") == "table"]
    rels = [d for d in docs if d.get("doc_type") == "relationship"]

    lines: List[str] = []
    lines.append("### TABLE METADATA (top matches)")
    for t in tables[:6]:
        sch = t.get("schema_name") or ""
        tbl = t.get("table_name") or ""
        bn = t.get("table_business_name") or ""
        desc = t.get("table_business_description") or ""
        lines.append(f"- {sch}.{tbl} | {bn} | {desc}".strip())

    lines.append("\n### RELATIONSHIPS (top matches)")
    for r in rels[:6]:
        fs = r.get("from_schema") or ""
        ft = r.get("from_table") or ""
        ts = r.get("to_schema") or ""
        tt = r.get("to_table") or ""
        jk = r.get("join_keys") or ""
        card = r.get("cardinality") or ""
        lines.append(f"- {fs}.{ft} -> {ts}.{tt} | {card} | join_keys: {jk}".strip())

    lines.append("\n### RAW SNIPPETS")
    for d in docs[:8]:
        lines.append(f"[{d.get('doc_type')}] { (d.get('content') or '')[:600] }")

    return "\n".join(lines)


_SQL_TABLE_RE = re.compile(r"\b(from|join)\s+([a-zA-Z0-9_]+)(?:\.)?([a-zA-Z0-9_]+)?", re.I)


def extract_tables_from_sql(sql: str) -> List[str]:
    """
    Rough extraction for guardrail checks.
    """
    found = []
    for m in _SQL_TABLE_RE.finditer(sql or ""):
        a = m.group(2)
        b = m.group(3)
        if b:
            found.append(f"{a}.{b}")
        else:
            found.append(a)
    return list(dict.fromkeys(found))


def llm_generate_sql_or_clarify(
    aoai: AzureOpenAI,
    question: str,
    context: str,
) -> Dict[str, Any]:
    """
    Returns JSON:
    - {"type":"sql","sql":"...","notes":"..."}
    - {"type":"clarify","questions":[...],"reason":"..."}
    - {"type":"answer","answer":"..."}  (greetings/simple)
    """
    sys = (
        "You are a text-to-SQL assistant.\n"
        "Use ONLY the provided metadata/relationships.\n"
        "If the question is ambiguous or tables/columns are unclear, ask clarification.\n"
        "Return STRICT JSON only (no markdown, no code fences).\n\n"
        "JSON schema:\n"
        "{\n"
        '  "type": "sql" | "clarify" | "answer",\n'
        '  "sql": "string (only if type=sql)",\n'
        '  "questions": ["..."] (only if type=clarify),\n'
        '  "reason": "string (only if type=clarify)",\n'
        '  "answer": "string (only if type=answer)",\n'
        '  "notes": "string (optional)"\n'
        "}\n"
    )

    user = f"USER QUESTION:\n{question}\n\nMETADATA CONTEXT:\n{context}\n"

    resp = aoai.chat.completions.create(
        model=chat_deployment(),
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
    )
    txt = (resp.choices[0].message.content or "").strip()

    # Robust JSON parse
    try:
        return json.loads(txt)
    except Exception:
        # fallback: try to extract first JSON object
        start = txt.find("{")
        end = txt.rfind("}")
        if start >= 0 and end > start:
            return json.loads(txt[start:end+1])
        raise RuntimeError(f"LLM did not return valid JSON:\n{txt[:800]}")


def llm_fix_sql(
    aoai: AzureOpenAI,
    question: str,
    bad_sql: str,
    error_msg: str,
    context: str,
) -> Dict[str, Any]:
    sys = (
        "You are a SQL expert.\n"
        "Fix the SQL using ONLY provided metadata.\n"
        "If the fix requires missing info, return clarify.\n"
        "Return STRICT JSON only.\n"
        'Schema: {"type":"sql"|"clarify","sql":"...","questions":[...],"reason":"...","notes":"..."}'
    )
    user = (
        f"QUESTION:\n{question}\n\n"
        f"FAILED SQL:\n{bad_sql}\n\n"
        f"ERROR:\n{error_msg}\n\n"
        f"METADATA CONTEXT:\n{context}\n"
    )
    resp = aoai.chat.completions.create(
        model=chat_deployment(),
        messages=[
            {"role": "system", "content": sys},
            {"role": "user", "content": user},
        ],
        temperature=0.1,
    )
    txt = (resp.choices[0].message.content or "").strip()
    try:
        return json.loads(txt)
    except Exception:
        start = txt.find("{")
        end = txt.rfind("}")
        if start >= 0 and end > start:
            return json.loads(txt[start:end+1])
        raise RuntimeError(f"LLM did not return valid JSON:\n{txt[:800]}")


def ask_question(question: str, search_client: SearchClient) -> Dict[str, Any]:
    """
    Main entry used by UI.
    Returns dict with keys:
    - type, sql, clarification, etc.
    """
    aoai = get_aoai_client()
    docs = search_metadata(search_client, aoai, question, top_k=8)
    context = build_context(docs)

    data = llm_generate_sql_or_clarify(aoai, question, context)

    # Guardrail: if type=sql but tables look made-up, ask clarify
    if data.get("type") == "sql":
        sql = (data.get("sql") or "").strip()
        used = extract_tables_from_sql(sql)

        # We only allow table names that appear in context as schema.table
        allowed = set()
        for d in docs:
            if d.get("doc_type") == "table":
                sch = d.get("schema_name") or ""
                tbl = d.get("table_name") or ""
                if sch and tbl:
                    allowed.add(f"{sch}.{tbl}")
                if tbl:
                    allowed.add(tbl)

        if used and not any(u in allowed for u in used):
            return {
                "type": "clarify",
                "questions": [
                    "Which exact table should I use for this metric?",
                    "Which schema/environment should the query target?",
                ],
                "reason": f"The generated SQL referenced tables not present in metadata: {used}",
                "context": context,
            }

        data["context"] = context
    else:
        data["context"] = context

    return data
