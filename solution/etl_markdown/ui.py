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
      --td-green: #0B7E3E;
      --td-green-dark: #075C2D;
      --td-border: #E5E7EB;
      --td-text: #111827;
      --td-subtext: #4B5563;
      --td-bg: #FFFFFF;
      --td-card: #FFFFFF;
    }

    body, .gradio-container { background: var(--td-bg) !important; }
    footer { display: none !important; }

    .td-page {
      max-width: 1180px;
      margin: 0 auto;
      padding: 18px 14px 18px 14px;
    }

    .td-header {
      display: flex;
      align-items: center;
      gap: 14px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--td-border);
      margin-bottom: 18px;
    }
    .td-logo img { height: 44px; width: auto; display: block; }
    .td-title {
      font-size: 24px;
      font-weight: 800;
      margin: 0;
      color: var(--td-text);
      line-height: 1.1;
    }
    .td-subtitle {
      margin: 6px 0 0 0;
      color: var(--td-subtext);
      font-size: 14px;
    }

    .td-card {
      border: 1px solid var(--td-border);
      border-radius: 16px;
      background: var(--td-card);
      padding: 14px;
      box-shadow: 0 2px 10px rgba(0,0,0,.05);
    }

    /* Primary button */
    .gr-button-primary, button.primary {
      background: var(--td-green) !important;
      border: none !important;
      color: white !important;
      border-radius: 12px !important;
      font-weight: 800 !important;
    }
    .gr-button-primary:hover, button.primary:hover {
      background: var(--td-green-dark) !important;
    }

    /* Inputs */
    textarea, input { border-radius: 12px !important; }

    /* Make tabs cleaner */
    .gradio-container .tabs { border-radius: 14px; }
    """

    header_html = f"""
    <div class="td-page">
      <div class="td-header">
        <div class="td-logo">
          {"<img src='" + logo_src + "' alt='TD Logo' />" if logo_src else "<div style='font-weight:900;color:#0B7E3E;font-size:22px;'>TD</div>"}
        </div>
        <div>
          <h1 class="td-title">AMCB TEXT2SQL</h1>
          <p class="td-subtitle">
            Ask a question in natural language. The system generates SQL using metadata search and (optionally) executes it.
          </p>
        </div>
      </div>
    </div>
    """

    with gr.Blocks(theme=theme, css=css, title="AMCB TEXT2SQL") as demo:
        gr.HTML(header_html)

        with gr.Group(elem_classes=["td-page"]):
            with gr.Row(equal_height=True):
                # LEFT: input card
                with gr.Column(scale=4):
                    with gr.Group(elem_classes=["td-card"]):
                        question = gr.Textbox(
                            label="Ask your question",
                            placeholder="Example: Show top 10 accounts by total balance for last month",
                            lines=3,
                        )
                        do_execute = gr.Checkbox(label="Execute SQL", value=True)
                        max_rows = gr.Slider(
                            minimum=50,
                            maximum=5000,
                            value=500,
                            step=50,
                            label="Max rows (preview)",
                        )

                        with gr.Row():
                            run_btn = gr.Button("Run", variant="primary")
                            clear_btn = gr.Button("Clear", variant="secondary")

                # RIGHT: outputs card with tabs
                with gr.Column(scale=6):
                    with gr.Group(elem_classes=["td-card"]):
                        status_md = gr.Markdown()
                        with gr.Tabs():
                            with gr.Tab("Result"):
                                result_grid = gr.Dataframe(
                                    label="SQL Result",
                                    interactive=False,
                                    wrap=True,
                                )
                            with gr.Tab("SQL"):
                                sql_out = gr.Code(label="Generated SQL", language="sql")

        run_btn.click(
            fn=lambda q, ex, mr: _run_text2sql(q, ex, int(mr), engine, search_client),
            inputs=[question, do_execute, max_rows],
            outputs=[sql_out, result_grid, status_md],
        )

        clear_btn.click(
            fn=lambda: ("", pd.DataFrame(), ""),
            inputs=None,
            outputs=[question, result_grid, status_md],
        )

    demo.launch(inbrowser=True, share=True)
