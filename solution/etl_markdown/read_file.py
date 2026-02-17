from __future__ import annotations

import base64
import datetime
from pathlib import Path
from typing import Any, Tuple

import gradio as gr
import pandas as pd
from sqlalchemy.engine import Engine

import os
from dotenv import load_dotenv

from ai_utils import generate_sql_or_clarify, ask_llm_to_fix_sql

load_dotenv(override=True)
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"


def _file_to_data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    ext = path.suffix.lower()
    mime = "image/png"
    if ext in [".jpg", ".jpeg"]:
        mime = "image/jpeg"
    elif ext == ".svg":
        mime = "image/svg+xml"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _fallback_execute_sql_df(sql: str, engine: Engine, max_rows: int = 500) -> Tuple[pd.DataFrame, str]:
    """
    Simple execution helper with preview limiting for SELECT-like queries.
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

        # SQL Server / Azure SQL
        if dialect in ("mssql", "pyodbc") and is_select and (" top " not in low[:50]):
            m = re.match(r"^\s*select(\s+distinct\s+)?", s2, flags=re.I)
            if m:
                distinct = m.group(1) or ""
                rest = s2[m.end():]
                return f"SELECT {distinct}TOP ({max_rows}) {rest}"

        return s2

    sql_limited = apply_preview_limit(sql)

    with engine.begin() as conn:
        low = sql_limited.strip().lower()
        if low.startswith("select") or low.startswith("with"):
            df = pd.read_sql_query(text(sql_limited), conn)
            status = f"✅ Returned {len(df)} row(s) (showing up to {max_rows})."
            return df, status

        res = conn.execute(text(sql_limited))
        return pd.DataFrame(), f"✅ Statement executed. Rows affected: {res.rowcount}"


def launch_ui(engine: Engine):
    assets_dir = Path(__file__).resolve().parent / "ICON"
    logo_path = assets_dir / "td_logo.png"
    logo_src = _file_to_data_uri(logo_path)

    css_path = Path(__file__).resolve().parent / "td_style.css"
    css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""

    theme = gr.themes.Soft(primary_hue="green", secondary_hue="green", neutral_hue="gray")

    header_html = f"""
    <div class="td-page">
      <div class="td-header">
        <div class="td-logo">
          {f"<img src='{logo_src}' alt='TD Logo' />" if logo_src else "<div style='font-weight:900;color:#0B7E3E;font-size:22px'>TD</div>"}
        </div>
        <div>
          <h1 class="td-title">AMCB TEXT2SQL</h1>
          <p class="td-subtitle">Ask a question in natural language. The system searches metadata, generates SQL, and (optionally) executes it.</p>
        </div>
      </div>
    </div>
    """

    def _run_text2sql(question: str, do_execute: bool, max_rows: int):
        def now():
            return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        q = (question or "").strip()
        if not q:
            yield "", pd.DataFrame(), "⚠️ Please enter a question.", "", ""
            return

        progress = []
        def log(msg: str):
            progress.append(f"[{now()}] {msg}")

        dialect = getattr(engine.dialect, "name", "sqlite") or "sqlite"

        log("Searching Azure AI Search metadata…")
        yield "", pd.DataFrame(), "⏳ Searching metadata…", "", "\n".join(progress)

        try:
            payload = generate_sql_or_clarify(q, engine_dialect=dialect)
        except Exception as e:
            log(f"Metadata/LLM error: {e}")
            yield "", pd.DataFrame(), f"❌ Error: {e}", "", "\n".join(progress)
            return

        if payload.get("action") == "clarify":
            clarify_q = payload.get("question", "Please clarify your request.")
            log("LLM requested clarification (not executing SQL).")
            status = "🟧 **Clarification needed** — please answer the question in the *Clarification* tab, then refine your request."
            clarification_md = f"### Clarification Needed\n\n{clarify_q}"
            yield "", pd.DataFrame(), status, clarification_md, "\n".join(progress)
            return

        sql = (payload.get("sql") or "").strip()
        if not sql:
            log("LLM returned empty SQL.")
            yield "", pd.DataFrame(), "❌ LLM returned empty SQL.", "", "\n".join(progress)
            return

        log("LLM generated SQL.")
        yield sql, pd.DataFrame(), "✅ SQL generated.", "", "\n".join(progress)

        if not do_execute:
            log("Execute SQL is OFF (stopping here).")
            yield sql, pd.DataFrame(), "✅ SQL generated. Turn on **Execute SQL** to run it.", "", "\n".join(progress)
            return

        # Execute with up to 2 fix attempts
        last_error = None
        current_sql = sql

        for attempt in range(1, 3):
            log(f"Executing SQL (attempt {attempt})…")
            yield current_sql, pd.DataFrame(), f"⏳ Executing SQL (attempt {attempt})…", "", "\n".join(progress)

            try:
                df, exec_status = _fallback_execute_sql_df(current_sql, engine, max_rows=max_rows)
                log("SQL executed successfully.")
                yield current_sql, df, exec_status, "", "\n".join(progress)
                return
            except Exception as e:
                last_error = str(e)
                log(f"SQL execution failed: {last_error}")

                # Ask LLM to fix, but it may request clarification
                try:
                    fix = ask_llm_to_fix_sql(q, current_sql, last_error, engine_dialect=dialect)
                except Exception as e2:
                    log(f"LLM fix step failed: {e2}")
                    yield current_sql, pd.DataFrame(), f"❌ SQL failed and fix step errored: {e2}", "", "\n".join(progress)
                    return

                if fix.get("action") == "clarify":
                    clarify_q = fix.get("question", "Please clarify your request.")
                    log("Fix step requested clarification (stopping).")
                    status = "🟧 **Clarification needed** — SQL cannot be executed safely without more info."
                    clarification_md = f"### Clarification Needed\n\n{clarify_q}\n\n**Last error:**\n\n`{last_error}`"
                    yield current_sql, pd.DataFrame(), status, clarification_md, "\n".join(progress)
                    return

                current_sql = (fix.get("sql") or "").strip()
                if not current_sql:
                    log("Fix step returned empty SQL.")
                    yield sql, pd.DataFrame(), f"❌ Fix attempt returned empty SQL. Last error: {last_error}", "", "\n".join(progress)
                    return

                log("LLM returned corrected SQL.")

        # After attempts
        yield current_sql, pd.DataFrame(), f"❌ SQL failed after 2 attempts.\n\n**Last error:** `{last_error}`", "", "\n".join(progress)

    with gr.Blocks(theme=theme, css=css, title="AMCB TEXT2SQL") as demo:
        gr.HTML(header_html)

        with gr.Group(elem_classes=["td-page"]):
            with gr.Row(equal_height=True):
                # LEFT
                with gr.Column(scale=4):
                    with gr.Group(elem_classes=["td-card"]):
                        question = gr.Textbox(
                            label="Ask your question",
                            placeholder="Example: Deposit count by day for last month",
                            lines=3,
                            elem_classes=["td-question-label"],
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

                # RIGHT
                with gr.Column(scale=6):
                    with gr.Group(elem_classes=["td-card"]):
                        status_md = gr.Markdown()
                        with gr.Tabs():
                            with gr.Tab("SQL"):
                                sql_out = gr.Code(label="Generated SQL", language="sql")
                            with gr.Tab("Result"):
                                result_grid = gr.Dataframe(
                                    label="SQL Result",
                                    interactive=False,
                                    wrap=True,
                                )
                            with gr.Tab("Clarification"):
                                clarification_md = gr.Markdown(
                                    value="If the model needs more info, it will appear here.",
                                )
                            with gr.Tab("Log"):
                                progress_md = gr.Markdown(value="")

        run_btn.click(
            fn=_run_text2sql,
            inputs=[question, do_execute, max_rows],
            outputs=[sql_out, result_grid, status_md, clarification_md, progress_md],
            show_progress=True,
            queue=True,
        )

        clear_btn.click(
            fn=lambda: ("", pd.DataFrame(), "", "If the model needs more info, it will appear here.", ""),
            inputs=None,
            outputs=[question, result_grid, status_md, clarification_md, progress_md],
        )

    demo.launch(server_name="0.0.0.0", server_port=7870, show_error=True, debug=True, inbrowser=True)
