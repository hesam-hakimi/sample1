from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from openai import AzureOpenAI


# ---------------------------
# Config
# ---------------------------

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# Set DB_DIALECT=sqlite to activate "no schema" logic
DB_DIALECT = os.getenv("DB_DIALECT", "sqlite").strip().lower()

# Azure AI Search
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "").strip()
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX", os.getenv("INDEX_NAME", "")).strip()

# Azure OpenAI
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21").strip()
AZURE_OPENAI_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "").strip()


# ---------------------------
# MSI-only credential (no browser tab, no az login)
# ---------------------------

def get_msi_credential() -> DefaultAzureCredential:
    """
    MSI-only:
    - no API keys
    - no az login
    - no interactive browser (prevents opening new tab)
    """
    return DefaultAzureCredential(
        exclude_interactive_browser_credential=True,
        exclude_visual_studio_code_credential=True,
        exclude_shared_token_cache_credential=True,
    )


def setup_azure_search() -> SearchClient:
    if not AZURE_SEARCH_ENDPOINT or not AZURE_SEARCH_INDEX:
        raise ValueError(
            "Missing AZURE_SEARCH_ENDPOINT or AZURE_SEARCH_INDEX (or INDEX_NAME). Set them in .env"
        )
    cred = get_msi_credential()
    return SearchClient(endpoint=AZURE_SEARCH_ENDPOINT, index_name=AZURE_SEARCH_INDEX, credential=cred)


# Backward-compatible alias (some codebases use this name)
def get_search_client() -> SearchClient:
    return setup_azure_search()


def _azure_openai_token_provider():
    cred = get_msi_credential()

    def provider() -> str:
        token = cred.get_token("https://cognitiveservices.azure.com/.default")
        return token.token

    return provider


def get_openai_client() -> AzureOpenAI:
    if not AZURE_OPENAI_ENDPOINT:
        raise ValueError("Missing AZURE_OPENAI_ENDPOINT in .env")
    if not AZURE_OPENAI_CHAT_DEPLOYMENT:
        raise ValueError("Missing AZURE_OPENAI_CHAT_DEPLOYMENT in .env")

    return AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_version=AZURE_OPENAI_API_VERSION,
        azure_ad_token_provider=_azure_openai_token_provider(),
    )


def get_openai_model_name() -> str:
    # AzureOpenAI uses deployment name as "model"
    return AZURE_OPENAI_CHAT_DEPLOYMENT


# ---------------------------
# Search helpers
# ---------------------------

@dataclass
class SearchHit:
    score: float
    doc: Dict[str, Any]


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    try:
        return json.dumps(x, ensure_ascii=False)
    except Exception:
        return str(x)


def _extract_best_text(doc: Dict[str, Any]) -> str:
    for k in ("content", "table_business_description", "business_description", "relationship_description"):
        if k in doc and isinstance(doc[k], str) and doc[k].strip():
            return doc[k].strip()
    return _safe_str(doc)


def search_metadata(question: str, search_client: SearchClient, *, top_k: int = 12) -> List[SearchHit]:
    """
    IMPORTANT:
    - Do NOT use select fields that might not exist (avoids schema_name select errors)
    """
    results = search_client.search(
        search_text=question,
        top=top_k,
        query_type="simple",
    )

    hits: List[SearchHit] = []
    for r in results:
        doc = dict(r)
        score = float(doc.get("@search.score", 0.0))
        hits.append(SearchHit(score=score, doc=doc))

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def build_metadata_context(hits: List[SearchHit], *, max_chars: int = 8000) -> str:
    parts: List[str] = []
    used = 0

    for h in hits:
        d = h.doc
        table_name = _safe_str(d.get("table_name") or d.get("to_table") or d.get("from_table") or "")
        schema_name = _safe_str(d.get("schema_name") or d.get("to_schema") or d.get("from_schema") or "")
        column_name = _safe_str(d.get("column_name") or "")
        kind = _safe_str(d.get("kind") or d.get("doc_type") or "")

        header_bits = []
        if kind:
            header_bits.append(f"kind={kind}")
        if schema_name:
            header_bits.append(f"schema={schema_name}")
        if table_name:
            header_bits.append(f"table={table_name}")
        if column_name:
            header_bits.append(f"column={column_name}")

        header = " | ".join(header_bits) if header_bits else "metadata"
        body = _extract_best_text(d)
        block = f"[{header}]\n{body}\n"

        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)

    return "\n".join(parts).strip()


def build_suggestions_from_hits(hits: List[SearchHit], keyword: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    kw = keyword.lower().strip()
    suggestions: List[Dict[str, Any]] = []

    for h in hits:
        d = h.doc
        table = _safe_str(d.get("table_name") or d.get("to_table") or d.get("from_table") or "")
        col = _safe_str(d.get("column_name") or "")
        content = _safe_str(d.get("content") or d.get("business_description") or d.get("table_business_description") or "")

        hay = f"{table} {col} {content}".lower()
        if kw and kw in hay:
            entry = {
                "table": table or "(unknown_table)",
                "columns": [col] if col else [],
                "reason": "Matched keyword in metadata",
            }
            if entry not in suggestions:
                suggestions.append(entry)

        if len(suggestions) >= limit:
            break

    return suggestions


# ---------------------------
# Prompts (fixed to prevent hallucinations)
# ---------------------------

def _sql_generation_prompt(
    question: str,
    db_dialect: str,
    metadata_context: str,
    relationship_context: str,
    suggestion_candidates: List[Dict[str, Any]],
) -> str:
    return f"""
You are a Text-to-SQL assistant.

You MUST follow these rules:
1) Use ONLY tables and columns that appear in METADATA CONTEXT.
   - If a column/table is not explicitly present, DO NOT use it.
   - Never invent columns (e.g., do NOT use RRDW_AS_OF_DATE unless it appears).
2) If DB_DIALECT is "sqlite":
   - NEVER use schema-qualified tables (no schema.table). Use only table_name.
3) Joins:
   - Use ONLY relationships present in RELATIONSHIP CONTEXT.
   - If joins are needed but unclear, return clarification with suggestions.

Output MUST be valid JSON only:
{{
  "type": "sql" | "clarification",
  "sql": "<SQL or empty>",
  "clarification": "<text or empty>",
  "suggestions": [
    {{"table":"<table>", "columns":["c1"], "reason":"<why>"}}
  ]
}}

DB_DIALECT: {db_dialect}

USER QUESTION:
{question}

SUGGESTION CANDIDATES:
{json.dumps(suggestion_candidates, ensure_ascii=False)}

METADATA CONTEXT:
{metadata_context}

RELATIONSHIP CONTEXT:
{relationship_context}

Return JSON only.
""".strip()


def _sql_fix_prompt(
    question: str,
    prev_sql: str,
    error_msg: str,
    db_dialect: str,
    metadata_context: str,
    relationship_context: str,
    suggestion_candidates: List[Dict[str, Any]],
) -> str:
    return f"""
You are fixing a SQL query that failed.

Rules:
1) Do NOT invent tables/columns. Use ONLY METADATA CONTEXT.
2) If DB_DIALECT is "sqlite", do NOT use schema-qualified tables.
3) If uncertain, return type="clarification" with suggestions.

Output MUST be valid JSON only:
{{
  "type": "sql" | "clarification",
  "sql": "<SQL or empty>",
  "clarification": "<text or empty>",
  "suggestions": [
    {{"table":"<table>", "columns":["c1"], "reason":"<why>"}}
  ]
}}

DB_DIALECT: {db_dialect}

USER QUESTION:
{question}

PREVIOUS SQL:
{prev_sql}

ERROR MESSAGE:
{error_msg}

SUGGESTION CANDIDATES:
{json.dumps(suggestion_candidates, ensure_ascii=False)}

METADATA CONTEXT:
{metadata_context}

RELATIONSHIP CONTEXT:
{relationship_context}

Return JSON only.
""".strip()


# ---------------------------
# Output handling
# ---------------------------

def _parse_llm_json(text: str) -> Dict[str, Any]:
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def _format_clarification(obj: Dict[str, Any]) -> str:
    clarification = (obj.get("clarification") or "").strip()
    suggestions = obj.get("suggestions") or []

    lines = ["I need more information to generate the correct SQL.\n"]
    if clarification:
        lines.append(clarification)
        lines.append("")

    if suggestions:
        lines.append("Suggested options (pick one or more):")
        for s in suggestions[:8]:
            table = s.get("table", "")
            cols = s.get("columns") or []
            reason = s.get("reason", "")
            cols_txt = ", ".join(cols) if cols else "(columns not specified)"
            lines.append(f"- **{table}** — columns: {cols_txt}" + (f" — {reason}" if reason else ""))

    return "\n".join(lines).strip()


def _normalize_sql(sql: str) -> str:
    s = (sql or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()
    return s.rstrip(";").strip()


def _strip_schema_for_sqlite(sql: str) -> str:
    # FROM schema.table -> FROM table
    sql = re.sub(r"(\bFROM\s+)([A-Za-z_]\w*)\.([A-Za-z_]\w*)", r"\1\3", sql, flags=re.I)
    # JOIN schema.table -> JOIN table
    sql = re.sub(r"(\bJOIN\s+)([A-Za-z_]\w*)\.([A-Za-z_]\w*)", r"\1\3", sql, flags=re.I)
    return sql


# ---------------------------
# Main API used by UI
# ---------------------------

def ask_question(question: str, search_client: SearchClient) -> str:
    q = (question or "").strip()
    if not q:
        return "I need more information to generate the correct SQL. Please enter a question."

    hits = search_metadata(q, search_client, top_k=14)
    metadata_ctx = build_metadata_context(hits, max_chars=9000)
    relationship_ctx = build_metadata_context(hits, max_chars=4500)

    keyword = "naics" if "naics" in q.lower() else ""
    suggestion_candidates = build_suggestions_from_hits(hits, keyword=keyword, limit=8) if keyword else []

    client = get_openai_client()
    model_name = get_openai_model_name()

    prompt = _sql_generation_prompt(
        question=q,
        db_dialect=DB_DIALECT,
        metadata_context=metadata_ctx or "(empty)",
        relationship_context=relationship_ctx or "(empty)",
        suggestion_candidates=suggestion_candidates,
    )

    resp = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    raw_text = (resp.choices[0].message.content or "").strip()

    obj = _parse_llm_json(raw_text)
    obj_type = (obj.get("type") or "").strip().lower()

    if obj_type == "clarification":
        return _format_clarification(obj)

    sql = _normalize_sql(obj.get("sql") or "")
    if not sql:
        return _format_clarification(
            {"clarification": "Please clarify your request.", "suggestions": suggestion_candidates[:8]}
        )

    if DB_DIALECT == "sqlite":
        sql = _strip_schema_for_sqlite(sql)

    return sql


def ask_llm_to_fix_sql(question: str, prev_sql: str, error_msg: str, search_client: SearchClient) -> str:
    q = (question or "").strip()
    prev = (prev_sql or "").strip()
    err = (error_msg or "").strip()

    hits = search_metadata(q, search_client, top_k=14)
    metadata_ctx = build_metadata_context(hits, max_chars=9000)
    relationship_ctx = build_metadata_context(hits, max_chars=4500)

    keyword = "naics" if "naics" in q.lower() else ""
    suggestion_candidates = build_suggestions_from_hits(hits, keyword=keyword, limit=8) if keyword else []

    client = get_openai_client()
    model_name = get_openai_model_name()

    prompt = _sql_fix_prompt(
        question=q,
        prev_sql=prev,
        error_msg=err,
        db_dialect=DB_DIALECT,
        metadata_context=metadata_ctx or "(empty)",
        relationship_context=relationship_ctx or "(empty)",
        suggestion_candidates=suggestion_candidates,
    )

    resp = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    raw_text = (resp.choices[0].message.content or "").strip()

    obj = _parse_llm_json(raw_text)
    obj_type = (obj.get("type") or "").strip().lower()

    if obj_type == "clarification":
        return _format_clarification(obj)

    sql = _normalize_sql(obj.get("sql") or "")
    if DB_DIALECT == "sqlite":
        sql = _strip_schema_for_sqlite(sql)
    return sql


# ---------------------------
# Backward-compatible function names (so imports won't break)
# ---------------------------

def llm_generate_sql(question: str, search_client: Optional[SearchClient] = None, *args, **kwargs) -> str:
    """
    Compatibility wrapper.
    Many repos call: llm_generate_sql(question, search_client)
    """
    if search_client is None:
        search_client = setup_azure_search()
    return ask_question(question, search_client)


def llm_fix_sql(
    question: str,
    prev_sql: str,
    error_msg: str,
    search_client: Optional[SearchClient] = None,
    *args,
    **kwargs,
) -> str:
    """
    Compatibility wrapper.
    Your code imports this name: from ai_utils import llm_fix_sql
    """
    if search_client is None:
        search_client = setup_azure_search()
    return ask_llm_to_fix_sql(question, prev_sql, error_msg, search_client)
