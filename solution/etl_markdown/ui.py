# ai_utils.py  (runtime retrieval + prompt context builder)
import os
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from dotenv import load_dotenv

from azure.identity import ManagedIdentityCredential, DefaultAzureCredential
from azure.core.credentials import AzureKeyCredential

from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

# ---- Your existing helpers ----
from embedding_utils import get_embedding, get_openai_client, get_openai_model_name


load_dotenv(override=True)


def get_credential():
    api_key = os.getenv("AISEARCH_API_KEY")
    if api_key:
        return AzureKeyCredential(api_key)

    client_id = os.getenv("CLIENT_ID")
    if client_id:
        return ManagedIdentityCredential(client_id=client_id)

    return DefaultAzureCredential(exclude_interactive_browser_credential=False)


def get_search_client() -> SearchClient:
    aisearch_account = os.getenv("AISEARCH_ACCOUNT")
    index_name = os.getenv("INDEX_NAME", "meta_data_field_v2")
    if not aisearch_account:
        raise ValueError("Missing AISEARCH_ACCOUNT in .env")
    endpoint = f"https://{aisearch_account}.search.windows.net"
    return SearchClient(endpoint=endpoint, index_name=index_name, credential=get_credential())


def infer_filter(question: str) -> Optional[str]:
    """
    Optional routing: when user explicitly asks for PII-only or PCI-only fields.
    Keep it conservative so you don't hide relevant results accidentally.
    """
    q = (question or "").lower()
    if "pii" in q or "personal information" in q or "personal data" in q:
        return "pii eq true"
    if "pci" in q or "credit card" in q or "payment card" in q:
        return "pci eq true"
    return None


def retrieve_field_metadata(
    search_client: SearchClient,
    question: str,
    top_k: int = 40,
    filter_expr: Optional[str] = None,
) -> List[Dict[str, Any]]:
    qvec = get_embedding(question)

    vector_query = VectorizedQuery(
        vector=qvec,
        k_nearest_neighbors=top_k,
        fields="content_vector",
    )

    results = search_client.search(
        search_text=question,              # keyword signal
        vector_queries=[vector_query],     # semantic signal
        top=top_k,
        filter=filter_expr,
        select=[
            "schema_name", "table_name", "column_name",
            "business_name", "business_description",
            "data_type", "allowed_values", "notes",
            "pii", "pci", "is_key", "is_filter_hint",
        ],
    )

    # Convert to plain dicts for easy formatting
    out: List[Dict[str, Any]] = []
    for r in results:
        out.append(dict(r))
    return out


def format_schema_context_markdown(
    docs: List[Dict[str, Any]],
    max_tables: int = 6,
    max_cols_per_table: int = 14,
) -> str:
    """
    GPT-ready context: grouped by table, field-level lines, compact & strict.
    """
    if not docs:
        return "## Schema Context (from Azure AI Search)\n\n(No matching schema metadata found.)"

    # Preserve table order by first appearance in ranked results
    ordered_tables: List[str] = []
    table_to_rows = defaultdict(list)

    for d in docs:
        schema = d.get("schema_name") or ""
        table = d.get("table_name") or ""
        key = f"{schema}.{table}".strip(".") if (schema or table) else "UNKNOWN_TABLE"
        if key not in table_to_rows:
            ordered_tables.append(key)
        table_to_rows[key].append(d)

    ordered_tables = ordered_tables[:max_tables]

    lines = ["## Schema Context (from Azure AI Search)\n"]
    for tkey in ordered_tables:
        lines.append(f"### Table: {tkey}")
        lines.append("Columns:")
        rows = table_to_rows[tkey][:max_cols_per_table]
        for r in rows:
            col = r.get("column_name") or "UNKNOWN_COLUMN"
            dt = r.get("data_type") or ""
            bd = (r.get("business_description") or r.get("business_name") or "").strip()
            pii = r.get("pii")
            pci = r.get("pci")
            is_key = r.get("is_key")

            meta_bits = []
            if pii is not None:
                meta_bits.append(f"PII={pii}")
            if pci is not None:
                meta_bits.append(f"PCI={pci}")
            if is_key is not None:
                meta_bits.append(f"is_key={is_key}")
            meta = (" | " + " ".join(meta_bits)) if meta_bits else ""

            desc = f" — {bd}" if bd else ""
            dtype = f" ({dt})" if dt else ""
            lines.append(f"- {col}{dtype}{desc}{meta}")

        lines.append("")  # spacing between tables

    return "\n".join(lines).strip()


def build_sql_prompt(schema_context_md: str, question: str) -> str:
    return f"""You are a SQL expert.

Rules:
- Use ONLY the tables/columns in "Schema Context". Do NOT invent names.
- If the user question cannot be answered with the provided schema context, ask ONE clarifying question.
- Output MUST be JSON with one of these shapes:

(1) For SQL:
{{"action":"sql","sql":"<single SQL query>"}}

(2) For clarification:
{{"action":"clarify","question":"<single question>"}}

Schema Context:
{schema_context_md}

User Question:
{question}
""".strip()


def generate_sql_or_clarify(question: str) -> str:
    """
    End-to-end runtime function:
    - retrieve schema context from Azure AI Search
    - build prompt
    - call OpenAI chat completion
    - return JSON string (sql or clarify)
    """
    sc = get_search_client()
    filter_expr = infer_filter(question)
    docs = retrieve_field_metadata(sc, question=question, top_k=40, filter_expr=filter_expr)
    schema_md = format_schema_context_markdown(docs)

    client = get_openai_client()
    model_name = get_openai_model_name()
    prompt = build_sql_prompt(schema_md, question)

    resp = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()
