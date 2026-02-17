# ui.py
from __future__ import annotations

import os
from typing import Any, Generator, Tuple
import pandas as pd
import gradio as gr
from sqlalchemy.engine import Engine
from azure.search.documents import SearchClient

from ai_utils import ask_question, get_aoai_client, llm_fix_sql
from db_utils import execute_sql_df


def _env_bool(name: str, default: bool = False) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    return v in {"1", "true", "yes", "y", "on"}


DEBUG_MODE = _env_bool("DEBUG_MODE", False)

TD_CSS = """
:root { --td-green: #0B7E3E; --td-bg: #F5F7F6; --td-card: #FFFFFF; --td-border: #D9E2DC; }
body { background: var(--td-bg) !important; }
.td-page { max-width: 1200px; margin: 0 auto; padding: 18px 12px; }
.td-header { display:flex; align-items:center; gap:12px; padding: 12px 14px; border:1px solid var(--td-border); border-radius:14px; background: var(--td-card); }
.td-title { font-size: 20px; font-weight: 800; margin: 0; color: #111; }
.td-subtitle { margin: 0; color: #444; font-size: 13px; }
.td-card { border:1px solid var(--td-border); border-radius:14px; background: var(--td-card); padding: 14px; }
.td-btn-primary button { background: var(--td-green) !important; border: none !important; }
.td-badge { display:inline-block; padding: 4px 10px; border-radius: 999px; background: rgba(11,126,62,.08); color: var(--td-green); font-weight:700; font-size: 12px; }
.td-warn { display:inline-block; padding: 8px 12px; border-radius: 12px; background: #FFF7E6; border:1px solid #FFE2A8; color:#5A3D00; font-weight:600; }
.td-error { display:inline-block; padding: 8px 12px; border-radius: 12px; background: #FFECEC; border:1px solid #FFC1C1; color:#7A0000; font-weight:700; }
"""

def _fmt_clarification(questions: list[str], reason: str) -> str:
    q_md = "\n".join([f"- **{q}**" for q in questions]) if questions else "- (No questions provided)"
    reason_md = reason or "More information is required to generate correct SQL."
    return (
        f"### ⚠️ I need clarification\n\n"
        f"{reason_md}\n\n"
        f"**Please answer:**\n{q_md}\n"
    )


def launch_ui(engine: Engine, search_client: SearchClient):
    header_html = """
    <div class="td-page">
      <div class="td-header">
        <div style="width:40px;height:40px;border-radius:10px;background:rgba(11,126,62,.10);display:flex;align-items:center;justify-content:center;">
          <span style="color:#0B7E3E;font-weight:900;">TD</span>
        </div>
        <div>
          <h1 class="td-title">AMCB TEXT2SQL</h1>
          <p class="td-subtitle">Ask a question in natural language. The system searches metadata, generates SQL, and (optionally) executes it.</p>
        </div>
        <div style="margin-left:auto;">
          <span class="td-badge">MSI-only</span>
        </div>
      </div>
    </div>
    """

    def run_flow(question: str, do_execute: bool, max_rows: int) -> Generator[Tuple[str, str, pd.DataFrame, str, str], None, None]:
        """
        Yields: (status_md, sql_code, result_df, clarification_md, log_md)
        """
        log_lines = []

        def log(msg: str):
            log_lines.append(msg)

        # Initial UI state
        yield ("", "", pd.DataFrame(), "", "Searching metadata...")

        q = (question or "").strip()
        if not q:
            yield ("<span class='td-warn'>Please enter a question.</span>", "", pd.DataFrame(), "", "")
            return

        try:
            log("🔎 Searching Azure AI Search metadata...")
            data = ask_question(q, search_client)
            log("✅ LLM decision received.")

            typ = data.get("type")

            if typ == "answer":
                ans = data.get("answer") or ""
                yield (f"<span class='td-badge'>Answer</span><br><br>{ans}", "", pd.DataFrame(), "", "\n".join(log_lines))
                return

            if typ == "clarify":
                clar = _fmt_clarification(data.get("questions") or [], data.get("reason") or "")
                yield ("<span class='td-warn'>Clarification required</span>", "", pd.DataFrame(), clar, "\n".join(log_lines))
                return

            if typ != "sql":
                yield ("<span class='td-error'>Unexpected response type from LLM.</span>", "", pd.DataFrame(), "", "\n".join(log_lines))
                return

            sql = (data.get("sql") or "").strip()
            if not sql:
                yield ("<span class='td-warn'>No SQL returned. Please refine the question.</span>", "", pd.DataFrame(), "", "\n".join(log_lines))
                return

            yield ("<span class='td-badge'>SQL generated</span>", sql, pd.DataFrame(), "", "\n".join(log_lines))

            if not do_execute:
                yield ("<span class='td-badge'>SQL generated (execution off)</span>", sql, pd.DataFrame(), "", "\n".join(log_lines))
                return

            # Execute attempt 1
            log(f"⚙️ Executing SQL (preview up to {max_rows})...")
            try:
                df, status = execute_sql_df(sql, engine, max_rows=max_rows)
                yield (status, sql, df, "", "\n".join(log_lines))
                return
            except Exception as e:
                err1 = str(e)
                log(f"❌ SQL execution failed: {err1}")

            # Fix attempt (LLM)
            log("🧠 Asking LLM to fix SQL based on error...")
            aoai = get_aoai_client()
            fixed = llm_fix_sql(aoai, q, sql, err1, data.get("context") or "")
            if fixed.get("type") == "clarify":
                clar = _fmt_clarification(fixed.get("questions") or [], fixed.get("reason") or "SQL failed and needs clarification.")
                yield ("<span class='td-warn'>Clarification required</span>", sql, pd.DataFrame(), clar, "\n".join(log_lines))
                return

            sql2 = (fixed.get("sql") or "").strip()
            if not sql2:
                yield ("<span class='td-error'>LLM could not fix the SQL.</span>", sql, pd.DataFrame(), "", "\n".join(log_lines))
                return

            log("✅ Got corrected SQL. Retrying execution...")
            try:
                df2, status2 = execute_sql_df(sql2, engine, max_rows=max_rows)
                yield (status2, sql2, df2, "", "\n".join(log_lines))
                return
            except Exception as e2:
                err2 = str(e2)
                log(f"❌ Second execution failed: {err2}")
                yield (f"<span class='td-error'>SQL execution failed after correction.</span><br><br>{err2}", sql2, pd.DataFrame(), "", "\n".join(log_lines))
                return

        except Exception as e:
            yield (f"<span class='td-error'>Error</span><br><br>{e}", "", pd.DataFrame(), "", "\n".join(log_lines))

    with gr.Blocks(css=TD_CSS, title="AMCB TEXT2SQL") as demo:
        gr.HTML(header_html)

        with gr.Row():
            with gr.Column(scale=4):
                with gr.Group(elem_classes=["td-card"]):
                    question = gr.Textbox(
                        label="Ask your question",
                        placeholder="Example: Deposit count by day",
                        lines=3,
                    )
                    do_execute = gr.Checkbox(label="Execute SQL", value=True)
                    max_rows = gr.Slider(minimum=50, maximum=5000, value=500, step=50, label="Max rows (preview)")

                    with gr.Row():
                        run_btn = gr.Button("Run", elem_classes=["td-btn-primary"])
                        clear_btn = gr.Button("Clear")

            with gr.Column(scale=6):
                with gr.Group(elem_classes=["td-card"]):
                    status_md = gr.HTML()

                    with gr.Tabs():
                        with gr.Tab("SQL"):
                            sql_out = gr.Code(label="Generated SQL", language="sql")
                        with gr.Tab("Result"):
                            result_grid = gr.Dataframe(label="SQL Result", interactive=False, wrap=True)
                        with gr.Tab("Clarification"):
                            clarification_md = gr.Markdown()
                        with gr.Tab("Log"):
                            log_md = gr.Markdown()

        run_btn.click(
            fn=run_flow,
            inputs=[question, do_execute, max_rows],
            outputs=[status_md, sql_out, result_grid, clarification_md, log_md],
            show_progress=True,
            queue=True,
        )

        clear_btn.click(
            fn=lambda: ("", "", pd.DataFrame(), "", ""),
            inputs=[],
            outputs=[status_md, sql_out, result_grid, clarification_md, log_md],
            queue=False,
        )

    # IMPORTANT: inbrowser=True only opens your app tab, not Azure login.
    demo.launch(server_name="0.0.0.0", server_port=7870, show_error=True, debug=DEBUG_MODE, inbrowser=True)
