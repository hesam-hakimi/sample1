# ui.py
# Modern Gradio UI (TD-style) for Text2SQL:
# - Left: question + options
# - Right: tabs (Result grid + SQL)
# - Logo embedded as base64 so it always shows
#
# Expected imports in your project:
#   - from ai_utils import ask_question
#   - from db_utils import execute_sql_df   (recommended helper returning (DataFrame, status_str))
#
# If you don't have execute_sql_df yet, see fallback implementation near the bottom.

from __future__ import annotations

import base64
from pathlib import Path
from typing import Tuple, Any

import gradio as gr
import pandas as pd
from sqlalchemy.engine import Engine
from azure.search.documents import SearchClient

from ai_utils import ask_question

# Prefer using a DB helper that returns a DataFrame for grid view:
# def execute_sql_df(sql: str, engine: Engine, max_rows: int = 500) -> Tuple[pd.DataFrame, str]
try:
    from db_utils import execute_sql_df  # type: ignore
except Exception:
    execute_sql_df = None  # fallback used if not available


def _file_to_data_uri(path: Path) -> str:
    """Embed an image so it reliably displays without static file routing."""
    if not path.exists():
        return ""
    ext = path.suffix.lower()
    if ext in [".jpg", ".jpeg"]:
        mime = "image/jpeg"
    elif ext == ".svg":
        mime = "image/svg+xml"
    else:
        mime = "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _fallback_execute_sql_df(sql: str, engine: Engine, max_rows: int = 500) -> Tuple[pd.DataFrame, str]:
    """
    Fallback if db_utils.execute_sql_df doesn't exist.
    NOTE: This is a best-effort preview limiter for common engines.
    """
    from sqlalchemy import text
    import re

    def apply_preview_limit(s: str) -> str:
        s2 = s.strip().rstrip(";")
        low = s2.lower()
        is_select = low.startswith("select")
        is_cte = low.startswith("with")
        if not (is_select or is_cte):
            return s2

        dialect = getattr(engine.dialect, "name", "").lower()

        if dialect == "sqlite":
            if re.search(r"\blimit\b", low):
                return s2
            return f"{s2} LIMIT {max_rows}"

        # Azure SQL / SQL Server
        if dialect == "mssql" and is_select and (" top " not in low[:40]):
            m = re.match(r"^\s*select\s+(distinct\s+)?", s2, flags=re.I)
            if m:
                distinct = m.group(1) or ""
                rest = s2[m.end() :]
                return f"SELECT {distinct}TOP ({max_rows}) {rest}"

        return s2

    sql_limited = apply_preview_limit(sql)

    with engine.begin() as conn:
        low = sql.strip().lower()
        if low.startswith("select") or low.startswith("with"):
            df = pd.read_sql_query(text(sql_limited), conn)
            status = f"✅ Returned {len(df)} rows (showing up to {max_rows})" if len(df) >= max_rows else f"✅ Returned {len(df)} rows"
            return df, status

        res = conn.execute(text(sql))
        return pd.DataFrame(), f"✅ Statement executed. Rows affected: {res.rowcount}"


def _run_text2sql(
    question: str,
    do_execute: bool,
    max_rows: int,
    engine: Engine,
    search_client: SearchClient,
) -> Tuple[str, pd.DataFrame, str]:
    """
    Returns: (generated_sql, result_df, status_markdown)
    """
    q = (question or "").strip()
    if not q:
        return "", pd.DataFrame(), "⚠️ Please enter a question."

    sql_query = ask_question(q, search_client)

    if not do_execute:
        return sql_query, pd.DataFrame(), "✅ SQL generated. Turn ON **Execute SQL** to run it."

    # Execute with df output (grid)
    if execute_sql_df is not None:
        df, status = execute_sql_df(sql_query, engine, max_rows=max_rows)  # type: ignore[misc]
        return sql_query, df, status

    df, status = _fallback_execute_sql_df(sql_query, engine, max_rows=max_rows)
    return sql_query, df, status


def launch_ui(engine: Engine, search_client: SearchClient):
    """
    Entry point used by your main.py
    """
    # --- Logo (put your logo here) ---
    # Recommended: <same folder as ui.py>/ICON/td_logo.png
    assets_dir = Path(__file__).resolve().parent / "ICON"
    logo_path = assets_dir / "td_logo.png"
    logo_src = _file_to_data_uri(logo_path)

    # --- Theme ---
    theme = gr.themes.Soft(primary_hue="green", secondary_hue="green", neutral_hue="gray")

    # --- Modern CSS (white + green, cards, tabs, spacing) ---
    css = """
    :root{
      --td-gree
