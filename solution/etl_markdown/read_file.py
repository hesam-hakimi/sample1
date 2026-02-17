from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient

# Azure OpenAI (OpenAI python SDK)
# pip install openai
from openai import AzureOpenAI


# ---------------------------
# Config
# ---------------------------

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"

# If you are using SQLite locally, set DB_DIALECT=sqlite
DB_DIALECT = os.getenv("DB_DIALECT", "sqlite").strip().lower()

# Azure AI Search
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "").strip()
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX", os.getenv("INDEX_NAME", "")).strip()

# Azure OpenAI
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21").strip()

# Deployments (names in Azure OpenAI "Deployments" page)
AZURE_OPENAI_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "").strip()
AZURE_OPENAI_EMBED_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT", "").strip()  # optional


# ---------------------------
# MSI-only credential
# ---------------------------

def get_msi_credential() -> DefaultAzureCredential:
    """
    MSI-only:
    - No API keys
    - No az login
    - No interactive browser (prevents opening new tab)
    """
    return DefaultAzureCredential(
        exclude_interactive_browser_credential=True,
        exclude_visual_studio_code_credential=True,   # avoids VSCode auth popups
        exclude_shared_token_cache_credential=True,   # avoids cached user prompts
    )


def setup_azure_search() -> SearchClient:
    if not AZURE_SEARCH_ENDPOINT or not AZURE_SEARCH_INDEX:
        raise ValueError(
            "Missing AZURE_SEARCH_ENDPOINT or AZURE_SEARCH_INDEX (or INDEX_NAME). "
            "Set them in your .env."
        )
    cred = get_msi_credential()
    return SearchClient(endpoint=AZURE_SEARCH_ENDPOINT, index_name=AZURE_SEARCH_INDEX, credential=cred)


def _azure_openai_token_provider():
    """
    Azure OpenAI with Entra ID (MSI): token scope is Cognitive Services.
    """
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
    # In AzureOpenAI, "model" is the DEPLOYMENT name
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
    """
    Try common fields:
    - content
    - table_business_description / field description, etc.
    - fallback: whole doc JSON
    """
    for k in ("content", "table_business_description", "business_description", "relationship_description"):
        if k in doc and isinstance(doc[k], str) and doc[k].strip():
            return doc[k].strip()
    return _safe_str(doc)


def search_metadata(
    question: str,
    search_client: SearchClient,
    *,
    top_k: int = 12,
) -> List[SearchHit]:
    """
    IMPORTANT:
    - Do NOT use $select fields that may not exist (prevents schema_name select errors).
    - Keep query simple and let the index decide what comes back.
    """
    results = search_client.search(
        search_text=question,
        top=top_k,
        query_type="simple",
    )

    hits: List[SearchHit] = []
    for r in results:
        # r is SearchDocument-like; convert to dict safely
        doc = dict(r)
        score = float(doc.get("@search.score", 0.0))
        hits.append(SearchHit(score=score, doc=doc))

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def build_metadata_context(hits: List[SearchHit], *, max_chars: int = 8000) -> str:
    """
    Build a compact context for the LLM from search hits.
    """
    parts: List[str] = []
    used = 0

    for h in hits:
        doc = h.doc
        table_name = _safe_str(doc.get("table_name") or doc.get("to_table") or doc.get("from_table") or "")
        schema_name = _safe_str(doc.get("schema_name") or doc.get("to_schema") or doc.get("from_schema") or "")
        column_name = _safe_str(doc.get("column_name") or "")
        kind = _safe_str(doc.get("kind") or doc.get("doc_type") or "")

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

        body = _extract_best_text(doc)
        block = f"[{header}]\n{body}\n"

        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)

    return "\n".join(parts).strip()


def build_relationship_context(hits: List[SearchHit], *, max_chars: int = 4000) -> str:
    """
    Relationship context can be the same hits, but we keep it smaller.
    If your index mixes doc types, the LLM will still filter based on text.
    """
    # Reuse the same logic but smaller budget
    return build_metadata_context(hits, max_chars=max_chars)


def build_suggestions_from_hits(hits: List[SearchHit], keyword: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    """
    Create suggestion candidates from metadata hits (helps NAICS scenario).
    This is NOT a big refactor — it's just shaping the context.
    """
    kw = keyword.lower().strip()
    suggestions: List[Dict[str, Any]] = []

    for h in hits:
        d = h.doc
        # pick plausible table/column fields if present
        table = _safe_str(d.get("table_name") or d.get("to_table") or d.get("from_table") or "")
        col = _safe_str(d.get("column_name") or "")
        content = _safe_str(d.get("content") or d.get("business_description") or d.get("table_business_description") or "")

        hay = f"{table} {col} {content}".lower()
        if kw and kw in hay:
            entry = {
                "table": table or "(unknown_table)",
                "columns": [col] if col else [],
                "reason": "Matched keyword in metadata context"
            }
            # dedupe
            if entry not in suggestions:
                suggestions.append(entry)

        if len(suggestions) >= limit:
            break

    return suggestions


# ---------------------------
# Prompts (fixed)
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
1) Use ONLY the tables and columns that appear in the provided METADATA CONTEXT.
   - If a column or table is not explicitly present in the context, DO NOT use it.
   - Never invent columns (example: do NOT use RRDW_AS_OF_DATE unless it appears in context).
2) If DB_DIALECT is "sqlite":
   - NEVER prefix tables with schema (no schema.table). Use only table_name.
   - Example: FROM v_dlv_dep_tran (NOT FROM rrdw_dlv.v_dlv_dep_tran)
3) If joins are needed:
   - Use ONLY relationships provided in RELATIONSHIP CONTEXT.
   - If relationships are missing/ambiguous, ask for clarification and suggest candidate joins found in the context.
4) If the question cannot be answered confidently from the context:
   - Return type="clarification"
   - Ask at most 2 short questions
   - Provide 3-8 concrete suggestions from context (tables/columns) the user can pick.

Output MUST be valid JSON only, with this schema:
{{
  "type": "sql" | "clarification",
  "sql": "<SQL string or empty>",
  "clarification": "<question to user or empty>",
  "suggestions": [
    {{"table": "<table_name>", "columns": ["col1","col2"], "reason": "<short reason>"}}
  ]
}}

DB_DIALECT: {db_dialect}

USER QUESTION:
{question}

SUGGESTION CANDIDATES (derived from metadata hits; you may reuse):
{json.dumps(suggestion_candidates, ensure_ascii=False)}

METADATA CONTEXT (tables + fields; only truth source):
{metadata_context}

RELATIONSHIP CONTEXT (only truth source for joins):
{relationship_context}

Now produce the JSON.
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
You are a SQL expert fixing a query that failed.

Rules:
1) Do NOT invent tables/columns. Use ONLY what exists in METADATA CONTEXT.
2) If DB_DIALECT is "sqlite", do NOT use schema-qualified names (no schema.table).
3) If the error is "no such table":
   - Propose a corrected query using the closest matching table name from METADATA CONTEXT.
   - If multiple candidates exist, return type="clarification" with suggestions.
4) If the error is "no such column":
   - Replace with the closest matching column(s) from METADATA CONTEXT.
   - If uncertain, return type="clarification" with suggestions.
5) Output MUST be valid JSON only:
{{
  "type": "sql" | "clarification",
  "sql": "<SQL string or empty>",
  "clarification": "<question to user or empty>",
  "suggestions": [
    {{"table": "<table_name>", "columns": ["col1","col2"], "reason": "<short reason>"}}
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

Now return the JSON.
""".strip()


# ---------------------------
# Output handling
# ---------------------------

def _parse_llm_json(text: str) -> Dict[str, Any]:
    """
    Handles:
    - accidental ```json fences
    - leading/trailing text
    """
    s = text.strip()

    # Remove code fences if present
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()

    # Try direct JSON
    try:
        return json.loads(s)
    except Exception:
        # Try to extract the first JSON object
        m = re.search(r"\{.*\}", s, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def _format_clarification(obj: Dict[str, Any]) -> str:
    clarification = (obj.get("clarification") or "").strip()
    suggestions = obj.get("suggestions") or []

    lines = []
    lines.append("I need more information to generate the correct SQL.\n")
    if clarification:
        lines.append(clarification.strip())
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


def _strip_schema_for_sqlite(sql: str) -> str:
    """
    Safety net: if DB is sqlite, remove schema prefixes only for FROM/JOIN targets.
    Keeps alias.column intact.
    """
    s = sql

    # FROM schema.table -> FROM table
    s = re.sub(r"(\bFROM\s+)([A-Za-z_]\w*)\.([A-Za-z_]\w*)", r"\1\3", s, flags=re.I)
    # JOIN schema.table -> JOIN table
    s = re.sub(r"(\bJOIN\s+)([A-Za-z_]\w*)\.([A-Za-z_]\w*)", r"\1\3", s, flags=re.I)

    return s


def _normalize_sql(sql: str) -> str:
    s = sql.strip()
    # remove fences if any
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()
    # remove trailing semicolon (optional)
    s = s.strip().rstrip(";").strip()
    return s


# ---------------------------
# Main function used by UI
# ---------------------------

def ask_question(question: str, search_client: SearchClient) -> str:
    """
    Returns:
    - SQL string (when ready)
    - Or a clarification message starting with "I need more information..." (UI already handles this)
    """
    q = (question or "").strip()
    if not q:
        return "I need more information to generate the correct SQL. Please enter a question."

    # 1) Retrieve metadata context
    hits = search_metadata(q, search_client, top_k=14)
    metadata_ctx = build_metadata_context(hits, max_chars=9000)
    relationship_ctx = build_relationship_context(hits, max_chars=4500)

    # Special keyword suggestions for common ambiguity cases
    # Example: NAICS
    keyword = "naics" if "naics" in q.lower() else ""
    suggestion_candidates = build_suggestions_from_hits(hits, keyword=keyword, limit=8) if keyword else []

    # 2) Ask LLM to produce JSON (sql or clarification)
    client = get_openai_client()
    model_name = get_openai_model_name()

    prompt = _sql_generation_prompt(
        question=q,
        db_dialect=DB_DIALECT,
        metadata_context=metadata_ctx or "(empty)",
        relationship_context=relationship_ctx or "(empty)",
        suggestion_candidates=suggestion_candidates,
    )

    if DEBUG_MODE:
        print("DEBUG: Prompt sent to LLM:\n", prompt[:2000], "\n---(truncated)---\n")

    resp = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )

    raw_text = resp.choices[0].message.content.strip()
    if DEBUG_MODE:
        print("DEBUG: Raw LLM response:\n", raw_text)

    try:
        obj = _parse_llm_json(raw_text)
    except Exception:
        # fallback to original behavior if parsing fails
        return raw_text.strip()

    obj_type = (obj.get("type") or "").strip().lower()

    if obj_type == "clarification":
        return _format_clarification(obj)

    sql = _normalize_sql(obj.get("sql") or "")
    if not sql:
        # if model returns type=sql but empty sql, treat as clarification
        return _format_clarification(
            {
                "clarification": "Please clarify your request (the system could not produce a valid SQL query).",
                "suggestions": suggestion_candidates[:8],
            }
        )

    # SQLite safety: strip schema from FROM/JOIN if it slipped through
    if DB_DIALECT == "sqlite":
        sql = _strip_schema_for_sqlite(sql)

    return sql


def ask_llm_to_fix_sql(
    question: str,
    prev_sql: str,
    error_msg: str,
    search_client: SearchClient,
) -> str:
    """
    Called when SQL execution fails, returns corrected SQL or clarification message.
    """
    q = (question or "").strip()
    prev = (prev_sql or "").strip()
    err = (error_msg or "").strip()

    hits = search_metadata(q, search_client, top_k=14)
    metadata_ctx = build_metadata_context(hits, max_chars=9000)
    relationship_ctx = build_relationship_context(hits, max_chars=4500)

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

    raw_text = resp.choices[0].message.content.strip()
    try:
        obj = _parse_llm_json(raw_text)
    except Exception:
        return raw_text.strip()

    obj_type = (obj.get("type") or "").strip().lower()
    if obj_type == "clarification":
        return _format_clarification(obj)

    sql = _normalize_sql(obj.get("sql") or "")
    if DB_DIALECT == "sqlite":
        sql = _strip_schema_for_sqlite(sql)
    return sql
