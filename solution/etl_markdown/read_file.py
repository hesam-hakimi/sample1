from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, Tuple

import gradio as gr
import pandas as pd
from sqlalchemy.engine import Engine
from azure.search.documents import SearchClient

# dotenv (keep it here as requested)
from dotenv import load_dotenv

load_dotenv()

DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() == "true"

from ai_utils import ask_question  # keep existing import

# Prefer using a DB helper that returns a DataFrame for grid view:
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
        if dialect == "mssql" and is_select and (" top " not in low[:60]):
            m = re.match(r"^\s*select\s+(distinct\s+)?", s2, flags=re.I)
            if m:
                distinct = m.group(1) or ""
                rest = s2[m.end() :]
                return f"SELECT {distinct}TOP ({max_rows}) {rest}"

        return s2

    sql_limited = apply_preview_limit(sql)

    with engine.begin() as conn:
        low = sql.strip().lower()
        if DEBUG_MODE:
            print(f"DEBUG: Executing SQL: {sql_limited}")

        if low.startswith("select") or low.startswith("with"):
            df = pd.read_sql_query(text(sql_limited), conn)
            status = f"✅ Returned {len(df)} rows (showing up to {max_rows})" if len(df) >= max_rows else f"✅ Returned {len(df)} rows"
            if DEBUG_MODE:
                print(f"DEBUG: Query result: {df.head()} (showing up to {max_rows})")
            return df, status

        res = conn.execute(text(sql))
        if DEBUG_MODE:
            print(f"DEBUG: Statement executed. Rows affected: {res.rowcount}")
        return pd.DataFrame(), f"✅ Statement executed. Rows affected: {res.rowcount}"


# ---------------------------
# ✅ FIX: accept str OR dict from ask_question()
# ---------------------------
def _coerce_llm_result_to_dict(result: Any) -> Dict[str, Any]:
    """
    Accepts:
      - dict (already structured)
      - str SQL
      - str JSON (e.g. {"sql": "..."} OR "SELECT ...")
    Returns a dict with at least one of: sql / clarification / error.
    """
    if isinstance(result, dict):
        return result

    if isinstance(result, str):
        s = result.strip()

        # Try parse JSON
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                return obj
            if isinstance(obj, str):
                return {"sql": obj.strip()}
        except Exception:
            pass

        # Plain text fallback
        low = s.lower()
        if low.startswith("i need") and "clarif" in low:
            return {"clarification": s}
        return {"sql": s}

    return {"sql": str(result)}


def _extract_sql_and_clarification(payload: Dict[str, Any]) -> Tuple[str, str]:
    sql_query = (
        payload.get("sql")
        or payload.get("sql_query")
        or payload.get("query")
        or payload.get("generated_sql")
        or ""
    )
    clarification = (
        payload.get("clarification")
        or payload.get("clarify")
        or payload.get("needs_clarification")
        or payload.get("message")
        or ""
    )

    # Normalize to strings
    if not isinstance(sql_query, str):
        sql_query = str(sql_query)
    if not isinstance(clarification, str):
        clarification = str(clarification)

    return sql_query.strip(), clarification.strip()


def _ask_llm_to_fix_sql(question: str, prev_sql: str, error_msg: str, search_client: SearchClient) -> str:
    # keep your existing approach: use ai_utils' OpenAI client/model helpers
    from ai_utils import get_openai_client, get_openai_model_name

    client = get_openai_client()
    model_name = get_openai_model_name()

    prompt = f"""
You are a SQL expert. The following SQL query failed to execute for the user's question.
Please correct the SQL based on the error message.

User question:
{question}

Previous SQL:
{prev_sql}

Error message:
{error_msg}

Return ONLY the corrected SQL (no explanations, no markdown).
""".strip()

    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
    )

    sql_query = response.choices[0].message.content.strip()

    # Remove code block markers if present
    if sql_query.startswith("```"):
        sql_query = sql_query.lstrip("`")
        if sql_query.lower().startswith("sql"):
            sql_query = sql_query[3:]
        sql_query = sql_query.rstrip("`").strip()

    return sql_query.strip()


def _run_text2sql(
    question: str,
    do_execute: bool,
    max_rows: int,
    engine: Engine,
    search_client: SearchClient,
) -> Any:
    """
    Returns a generator yielding (generated_sql, result_df, status_markdown, progress_log) step-by-step.
    """
    import datetime

    def now() -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    q = (question or "").strip()
    if not q:
        yield "", pd.DataFrame(), "⚠️ Please enter a question.", ""
        return

    progress_log = []
    if DEBUG_MODE:
        print(f"DEBUG: _run_text2sql called with question: {question}")

    progress_log.append(f"[{now()}] Searching Azure AI Search metadata...")
    yield "", pd.DataFrame(), "⏳ Searching metadata...", "\n".join(progress_log)

    progress_log.append(f"[{now()}] Sending request to LLM for SQL generation...")
    yield "", pd.DataFrame(), "⏳ Generating SQL...", "\n".join(progress_log)

    # ✅ FIXED: handle str/dict from ask_question without .get() crash
    raw = ask_question(q, search_client)
    payload = _coerce_llm_result_to_dict(raw)
    sql_query, clarification = _extract_sql_and_clarification(payload)

    progress_log.append(f"[{now()}] LLM returned response.")
    clarification_msg = "I need more information to generate the correct SQL. Please clarify your request."

    # If LLM asks for clarification (either explicit field OR classic text)
    if clarification or sql_query.lower().startswith("i need more information"):
        msg = clarification or clarification_msg
        yield "", pd.DataFrame(), f"⚠️ {msg}", "\n".join(progress_log)
        return

    progress_log.append(f"[{now()}] SQL generated.")
    yield sql_query, pd.DataFrame(), "✅ SQL generated.", "\n".join(progress_log)

    if not do_execute:
        progress_log.append(f"[{now()}] Waiting for user to execute SQL.")
        yield sql_query, pd.DataFrame(), "✅ SQL generated. Turn on **Execute SQL** to run it.", "\n".join(progress_log)
        return

    last_error = None
    for attempt in range(1, 6):
        progress_log.append(f"[{now()}] Executing SQL (Attempt {attempt})...")
        yield sql_query, pd.DataFrame(), f"⏳ Executing SQL (Attempt {attempt})...", "\n".join(progress_log)

        try:
            if execute_sql_df is not None:
                df, status = execute_sql_df(sql_query, engine, max_rows=max_rows)  # type: ignore[misc]
                progress_log.append(f"[{now()}] SQL executed successfully.")
                yield sql_query, df, status, "\n".join(progress_log)
                return

            df, status = _fallback_execute_sql_df(sql_query, engine, max_rows=max_rows)
            progress_log.append(f"[{now()}] SQL executed successfully.")
            yield sql_query, df, status, "\n".join(progress_log)
            return

        except Exception as e:
            last_error = str(e)
            progress_log.append(f"[{now()}] SQL execution failed: {last_error}")
            yield sql_query, pd.DataFrame(), f"❌ SQL execution failed: {last_error}", "\n".join(progress_log)

            if attempt == 2:
                break

            progress_log.append(f"[{now()}] Sending error and query back to LLM for correction...")
            yield sql_query, pd.DataFrame(), "⏳ Asking LLM to fix SQL...", "\n".join(progress_log)

            sql_query = _ask_llm_to_fix_sql(q, sql_query, last_error, search_client)

            # If fix attempt produced a clarification message
            if sql_query.strip().lower().startswith("i need more information"):
                yield "", pd.DataFrame(), f"⚠️ {clarification_msg}", "\n".join(progress_log)
                return

            progress_log.append(f"[{now()}] LLM returned corrected SQL.")
            yield sql_query, pd.DataFrame(), "✅ LLM returned corrected SQL.", "\n".join(progress_log)

    progress_log.append(f"[{now()}] All attempts failed.")
    yield sql_query, pd.DataFrame(), f"❌ SQL execution error after 2 attempts: {last_error}", "\n".join(progress_log)


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

    # --- Modern CSS loaded from external file ---
    css_path = Path(__file__).resolve().parent / "td_style.css"
    css = css_path.read_text(encoding="utf-8") if css_path.exists() else ""

    header_html = f"""
<div class="td-page">
  <div class="td-header">
    <div class="td-logo">
      {f"<img src='{logo_src}' alt='TD Logo' />" if logo_src else "<div style='font-weight:900;color:#0B7E3E;'>TD</div>"}
    </div>
    <div>
      <h1 class="td-title">AMCB TEXT2SQL</h1>
      <p class="td-subtitle">Ask a question in natural language. The system searches metadata, generates SQL, and (optionally) executes it.</p>
    </div>
  </div>
</div>
""".strip()

    def run_text2sql_wrapper(q, ex, mr):
        yield from _run_text2sql(q, ex, int(mr), engine, search_client)

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

                        show_log = gr.Checkbox(label="Show Log", value=True)

                # RIGHT: outputs card
                with gr.Column(scale=6):
                    with gr.Group(elem_classes=["td-card"]):
                        status_md = gr.Markdown()
                        with gr.Tabs():
                            with gr.Tab("SQL"):
                                sql_out = gr.Code(label="Generated SQL", language="sql")
                            with gr.Tab("Result"):
                                result_grid = gr.Dataframe(label="SQL Result", interactive=False, wrap=True)

                        progress_md = gr.Markdown(label="Progress Log", visible=True)

        def toggle_log(log_text, show):
            return log_text if show else ""

        run_btn.click(
            fn=run_text2sql_wrapper,
            inputs=[question, do_execute, max_rows],
            outputs=[sql_out, result_grid, status_md, progress_md],
            show_progress=True,
            queue=True,
        )

        show_log.change(
            fn=toggle_log,
            inputs=[progress_md, show_log],
            outputs=progress_md,
        )

        clear_btn.click(
            fn=lambda: ("", pd.DataFrame(), "", ""),
            inputs=None,
            outputs=[question, result_grid, status_md, progress_md],
        )

    demo.launch(server_name="0.0.0.0", server_port=7870, show_error=True, debug=True, inbrowser=True)
