from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Generator, Tuple

import gradio as gr
import pandas as pd
from sqlalchemy.engine import Engine
from azure.search.documents import SearchClient

from ai_utils import ask_question, ask_llm_to_fix_sql
from db_utils import execute_sql_df


DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"


def _file_to_data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    import base64
    mime = "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _clarification_md(payload: dict) -> str:
    qs = payload.get("questions") or []
    notes = payload.get("notes") or ""
    out = []
    out.append("### I need a bit more info\n")
    if qs:
        out.append("Please answer:\n")
        for i, q in enumerate(qs, 1):
            out.append(f"{i}. {q}")
    if notes:
        out.append("\n---\n")
        out.append(f"**Notes:** {notes}")
    return "\n".join(out).strip()


def _run_text2sql(
    question: str,
    do_execute: bool,
    max_rows: int,
    engine: Engine,
    search_client: SearchClient,
) -> Generator[Tuple[str, pd.DataFrame, str, str, str], None, None]:
    """
    Outputs:
      sql_out, result_df, clarification_md, status_md, log_md
    """
    q = (question or "").strip()
    if not q:
        yield "", pd.DataFrame(), "", "⚠️ Please enter a question.", ""
        return

    logs = []
    logs.append(f"[{q}]")

    # Step 1: ask question (metadata + LLM)
    yield "", pd.DataFrame(), "", "⏳ Searching metadata & generating SQL...", "\n".join(logs)

    payload, step_logs, known_schemas = ask_question(q, search_client, engine)
    logs.extend(step_logs)

    if payload.get("type") == "clarification":
        clar = _clarification_md(payload)
        yield "", pd.DataFrame(), clar, "🟨 Clarification needed.", "\n".join(logs)
        return

    sql = (payload.get("sql") or "").strip()
    if not sql:
        clar = _clarification_md(
            {
                "questions": ["I couldn't generate SQL. Can you rephrase the question or specify the table?"],
                "notes": payload.get("notes", ""),
            }
        )
        yield "", pd.DataFrame(), clar, "🟨 Clarification needed.", "\n".join(logs)
        return

    yield sql, pd.DataFrame(), "", "✅ SQL generated.", "\n".join(logs)

    # Step 2: execute (optional)
    if not do_execute:
        yield sql, pd.DataFrame(), "", "✅ SQL generated. Turn on Execute SQL to run it.", "\n".join(logs)
        return

    attempt_sql = sql
    last_err = None

    for attempt in range(1, 3):
        try:
            logs.append(f"[{attempt}] Executing SQL...")
            yield attempt_sql, pd.DataFrame(), "", f"⏳ Executing SQL (attempt {attempt})...", "\n".join(logs)

            df, msg = execute_sql_df(attempt_sql, engine, max_rows=max_rows)
            logs.append(msg)
            yield attempt_sql, df, "", msg, "\n".join(logs)
            return
        except Exception as e:
            last_err = str(e)
            logs.append(f"❌ Execution failed: {last_err}")

            # Ask LLM to fix SQL
            fix_payload, fix_logs = ask_llm_to_fix_sql(
                question=q,
                prev_sql=attempt_sql,
                error_msg=last_err,
                search_client=search_client,
                engine=engine,
                known_schemas=known_schemas,
            )
            logs.extend(fix_logs)

            if fix_payload.get("type") == "clarification":
                clar = _clarification_md(fix_payload)
                yield attempt_sql, pd.DataFrame(), clar, "🟨 Clarification needed (after SQL error).", "\n".join(logs)
                return

            fixed_sql = (fix_payload.get("sql") or "").strip()
            if not fixed_sql:
                break
            attempt_sql = fixed_sql
            logs.append("✅ Got corrected SQL from LLM.")
            yield attempt_sql, pd.DataFrame(), "", "✅ Got corrected SQL. Retrying execution...", "\n".join(logs)

    yield attempt_sql, pd.DataFrame(), "", f"🟥 SQL execution failed: {last_err}", "\n".join(logs)


def launch_ui(engine: Engine, search_client: SearchClient) -> None:
    # --- Assets ---
    assets_dir = Path(__file__).resolve().parent / "ICON"
    logo_src = _file_to_data_uri(assets_dir / "td_logo.png")

    css = """
    .td-page { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial; }
    .td-header { display:flex; align-items:center; gap:14px; padding:16px 18px; border:1px solid #d9e6df; border-radius:14px; background:#f7fbf8; }
    .td-title { font-size:22px; font-weight:800; margin:0; }
    .td-sub { margin:0; color:#335a46; font-size:13px; }
    .td-badge { margin-left:auto; font-size:12px; padding:6px 10px; border-radius:999px; background:#e7f5ec; border:1px solid #cfe8d8; color:#1f6b44; font-weight:700;}
    .td-card { border:1px solid #d9e6df; border-radius:14px; background:white; padding:14px; box-shadow: 0 1px 0 rgba(0,0,0,.02); }
    .td-btn button { border-radius:12px !important; font-weight:800 !important; }
    .td-status { border-radius:12px; padding:10px 12px; background:#f7fbf8; border:1px solid #d9e6df; }
    """

    header_html = f"""
    <div class="td-page">
      <div class="td-header">
        <div style="width:42px;height:42px;display:flex;align-items:center;justify-content:center;border-radius:10px;background:#e7f5ec;border:1px solid #cfe8d8;">
          {f'<img src="{logo_src}" style="width:28px;height:28px;object-fit:contain;" />' if logo_src else '<span style="font-weight:900;color:#1f6b44;">TD</span>'}
        </div>
        <div>
          <h1 class="td-title">AMCB TEXT2SQL</h1>
          <p class="td-sub">Ask in natural language. The system searches metadata, generates SQL, and (optionally) executes it.</p>
        </div>
        <div class="td-badge">MSI-only</div>
      </div>
    </div>
    """

    with gr.Blocks(css=css, title="AMCB TEXT2SQL") as demo:
        gr.HTML(header_html)
        status_md = gr.Markdown(value="", elem_classes=["td-status"])

        with gr.Row(equal_height=True):
            with gr.Column(scale=4):
                with gr.Group(elem_classes=["td-card"]):
                    question = gr.Textbox(
                        label="Ask your question",
                        placeholder="Example: Deposit count by day (using transaction date) for last 30 days",
                        lines=3,
                    )
                    do_execute = gr.Checkbox(label="Execute SQL", value=True)
                    max_rows = gr.Slider(minimum=50, maximum=5000, value=500, step=50, label="Max rows (preview)")

                    with gr.Row():
                        run_btn = gr.Button("Run", variant="primary", elem_classes=["td-btn"])
                        clear_btn = gr.Button("Clear", variant="secondary", elem_classes=["td-btn"])

            with gr.Column(scale=6):
                with gr.Group(elem_classes=["td-card"]):
                    with gr.Tabs():
                        with gr.Tab("SQL"):
                            sql_out = gr.Code(label="Generated SQL", language="sql")
                        with gr.Tab("Result"):
                            result_df = gr.Dataframe(label="SQL Result", interactive=False, wrap=True)
                        with gr.Tab("Clarification"):
                            clar_md = gr.Markdown(value="")
                        with gr.Tab("Log"):
                            log_md = gr.Markdown(value="")

        def runner(q, ex, mr):
            yield from _run_text2sql(q, ex, int(mr), engine, search_client)

        run_btn.click(
            fn=runner,
            inputs=[question, do_execute, max_rows],
            outputs=[sql_out, result_df, clar_md, status_md, log_md],
            show_progress=True,
            queue=True,
        )

        clear_btn.click(
            fn=lambda: ("", pd.DataFrame(), "", "", ""),
            inputs=None,
            outputs=[question, result_df, clar_md, status_md, log_md],
        )

        demo.launch(server_name="0.0.0.0", server_port=7870, show_error=True, debug=True, inbrowser=True)
