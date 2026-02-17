from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Generator, Tuple

import gradio as gr
import pandas as pd
from sqlalchemy.engine import Engine
from azure.search.documents import SearchClient

from ai_utils import (
    get_msi_credential,
    get_aoai_client,
    get_search_clients,
    search_metadata,
    build_context,
    generate_sql_or_clarification,
    fix_sql_on_error,
    strip_schema_for_sqlite,
    validate_sql_against_db,
)
from db_utils import execute_sql_df, get_table_schemas


DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
MAX_SEARCH_HITS = int(os.getenv("MAX_SEARCH_HITS", "12"))


def _read_css() -> str:
    css_path = Path(__file__).resolve().parent / "td_style.css"
    return css_path.read_text(encoding="utf-8") if css_path.exists() else ""


def _status_box(msg: str, kind: str = "success") -> str:
    kind = kind if kind in ("success", "warn", "danger") else "success"
    safe = (msg or "").replace("<", "&lt;").replace(">", "&gt;")
    return f'<div class="td-status {kind}">{safe}</div>'


def launch_ui(engine: Engine, search_client: SearchClient) -> None:
    css = _read_css()

    # Header HTML
    header_html = f"""
    <div class="td-page">
      <div class="td-header">
        <div class="td-logo">
          <div style="width:42px;height:42px;border-radius:12px;background:rgba(11,126,62,0.10);display:flex;align-items:center;justify-content:center;font-weight:900;color:#0b7e3e;">
            TD
          </div>
        </div>
        <div>
          <h1 class="td-title">AMCB TEXT2SQL</h1>
          <p class="td-subtitle">Ask a question in natural language. The system searches metadata, generates SQL, and (optionally) executes it.</p>
        </div>
        <div class="td-badge">MSI-only</div>
      </div>
    </div>
    """

    table_schemas = get_table_schemas(engine)
    dialect = (engine.dialect.name or "").lower()

    # MSI clients
    cred = get_msi_credential()
    aoai = get_aoai_client(cred)

    # Optional vector dim
    vector_dim_env = os.getenv("VECTOR_DIM", "").strip()
    vector_dim = int(vector_dim_env) if vector_dim_env else None

    def run_flow(question: str, do_execute: bool, max_rows: int) -> Generator[Tuple[str, pd.DataFrame, str, str, str], None, None]:
        q = (question or "").strip()
        if not q:
            yield "", pd.DataFrame(), "", _status_box("Please enter a question.", "warn"), ""
            return

        log_lines = []
        def log(s: str):
            log_lines.append(s)
            return "\n".join(log_lines)

        yield "", pd.DataFrame(), "", _status_box("Searching metadata...", "success"), log(f"[1] Searching Azure AI Search for: {q}")

        # 1) Retrieve
        hits = search_metadata(aoai, search_client, q, vector_dim=vector_dim, top_k=MAX_SEARCH_HITS)
        ctx, known_schemas = build_context(hits, table_schemas, dialect=dialect)

        if DEBUG_MODE:
            log(f"[debug] hits={len(hits)} dialect={dialect}")

        # 2) Ask LLM for SQL or clarification
        yield "", pd.DataFrame(), "", _status_box("Generating SQL...", "success"), log("[2] Sending context to LLM for SQL generation...")

        obj = generate_sql_or_clarification(aoai, q, ctx)

        if obj.get("type") == "clarification":
            qs = obj.get("questions") or []
            clar_md = "### I need a bit more info\n" + "\n".join([f"- {x}" for x in qs[:10]])
            yield "", pd.DataFrame(), clar_md, _status_box("Clarification needed.", "warn"), log("[2] LLM asked for clarification.")
            return

        sql = (obj.get("sql") or "").strip()
        if not sql:
            yield "", pd.DataFrame(), "### Clarification\n- I couldn't generate SQL. Please clarify the target tables.", _status_box("Clarification needed.", "warn"), log("[2] Empty SQL from LLM.")
            return

        # SQLite: strip schema prefixes if present
        if dialect == "sqlite":
            sql = strip_schema_for_sqlite(sql, known_schemas, list(table_schemas.keys()))

        # Validate referenced tables exist (sqlite)
        missing_msg = validate_sql_against_db(sql, table_schemas, dialect=dialect)
        if missing_msg:
            clar_md = "### I need a bit more info\n" + f"- {missing_msg}\n- Which table should be used instead?"
            yield sql, pd.DataFrame(), clar_md, _status_box("Clarification needed (table not found).", "warn"), log("[2] SQL references a missing table.")
            return

        yield sql, pd.DataFrame(), "", _status_box("SQL generated.", "success"), log("[2] SQL generated successfully.")

        # 3) Execute (optional)
        if not do_execute:
            yield sql, pd.DataFrame(), "", _status_box("Execution is OFF. Turn on 'Execute SQL' to run it.", "warn"), log("[3] Skipping execution (toggle off).")
            return

        try:
            yield sql, pd.DataFrame(), "", _status_box("Executing SQL...", "success"), log("[3] Executing SQL...")
            df, status = execute_sql_df(engine, sql, max_rows=int(max_rows))
            yield sql, df, "", _status_box(status, "success"), log("[3] SQL executed.")
            return
        except Exception as e:
            err = str(e)
            yield sql, pd.DataFrame(), "", _status_box("Execution failed. Attempting correction...", "warn"), log(f"[3] Execution error: {err}")

            # Ask LLM to fix SQL (1 attempt)
            obj2 = fix_sql_on_error(aoai, q, sql, err, ctx)
            if obj2.get("type") == "clarification":
                qs = obj2.get("questions") or []
                clar_md = "### I need a bit more info\n" + "\n".join([f"- {x}" for x in qs[:10]])
                yield sql, pd.DataFrame(), clar_md, _status_box("Clarification needed.", "warn"), log("[4] LLM asked for clarification after error.")
                return

            sql2 = (obj2.get("sql") or "").strip()
            if dialect == "sqlite":
                sql2 = strip_schema_for_sqlite(sql2, known_schemas, list(table_schemas.keys()))

            missing_msg2 = validate_sql_against_db(sql2, table_schemas, dialect=dialect)
            if missing_msg2:
                clar_md = "### I need a bit more info\n" + f"- {missing_msg2}\n- Which table should be used instead?"
                yield sql2, pd.DataFrame(), clar_md, _status_box("Clarification needed (table not found).", "warn"), log("[4] Fixed SQL references a missing table.")
                return

            try:
                df2, status2 = execute_sql_df(engine, sql2, max_rows=int(max_rows))
                yield sql2, df2, "", _status_box(status2, "success"), log("[4] Corrected SQL executed.")
                return
            except Exception as e2:
                err2 = str(e2)
                clar_md = "### Execution failed\n" + f"- {err2}\n- Please specify the exact table name and required filters."
                yield sql2, pd.DataFrame(), clar_md, _status_box("SQL execution failed after correction.", "danger"), log(f"[4] Corrected SQL failed: {err2}")
                return

    with gr.Blocks(css=css, title="AMCB TEXT2SQL") as demo:
        gr.HTML(header_html)

        with gr.Row(equal_height=True):
            with gr.Column(scale=4):
                with gr.Group(elem_classes=["td-card"]):
                    gr.Markdown('<div class="td-section-title">Input</div>')
                    question = gr.Textbox(
                        label="Ask your question",
                        placeholder="Example: Deposit count by day for last month",
                        lines=3,
                    )
                    do_execute = gr.Checkbox(label="Execute SQL", value=True)
                    max_rows = gr.Slider(minimum=50, maximum=5000, value=500, step=50, label="Max rows (preview)")
                    with gr.Row():
                        run_btn = gr.Button("Run", elem_classes=["td-primary-btn"])
                        clear_btn = gr.Button("Clear", elem_classes=["td-secondary-btn"])

            with gr.Column(scale=6):
                with gr.Group(elem_classes=["td-card"]):
                    status = gr.HTML(value=_status_box("Ready.", "success"))
                    with gr.Tabs(elem_classes=["td-tabs"]) as tabs:
                        with gr.Tab("SQL"):
                            sql_out = gr.Code(label="Generated SQL", language="sql")
                        with gr.Tab("Result"):
                            result_df = gr.Dataframe(label="SQL Result", interactive=False, wrap=True)
                        with gr.Tab("Clarification"):
                            clar_out = gr.Markdown(value="If clarification is needed, it will appear here.")
                        with gr.Tab("Log"):
                            log_out = gr.Markdown(value="")

        run_btn.click(
            fn=run_flow,
            inputs=[question, do_execute, max_rows],
            outputs=[sql_out, result_df, clar_out, status, log_out],
            show_progress=True,
            queue=True,
        )

        clear_btn.click(
            fn=lambda: ("", pd.DataFrame(), "If clarification is needed, it will appear here.", _status_box("Ready.", "success"), ""),
            inputs=[],
            outputs=[question, result_df, clar_out, status, log_out],
            queue=False,
        )

    demo.launch(server_name="0.0.0.0", server_port=7870, show_error=True, debug=DEBUG_MODE, inbrowser=True)
