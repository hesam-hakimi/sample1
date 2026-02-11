import base64
from pathlib import Path

import gradio as gr
from sqlalchemy.engine import Engine
from azure.search.documents import SearchClient

from ai_utils import ask_question
from db_utils import execute_sql


def _file_to_data_uri(path: Path) -> str:
    """
    Embeds an image into HTML reliably (no /file routing, no allowed_paths needed).
    """
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


def gradio_ask_question(user_question: str, do_execute: bool, engine: Engine, search_client: SearchClient):
    sql_query = ask_question(user_question, search_client)

    if not do_execute:
        return sql_query, "✅ SQL generated. Turn ON “Execute SQL” to run it."

    result = execute_sql(sql_query, engine)

    # Make result display-safe regardless of type
    try:
        # If it's already a string, show it
        if isinstance(result, str):
            return sql_query, result

        # If it's rows (list of dicts / tuples), try to format nicely
        import pandas as pd  # optional, but usually available
        if isinstance(result, pd.DataFrame):
            return sql_query, result.to_string(index=False)

        if isinstance(result, (list, tuple)):
            df = pd.DataFrame(result)
            return sql_query, df.to_string(index=False)

    except Exception:
        pass

    return sql_query, str(result)


def launch_ui(engine: Engine, search_client: SearchClient):
    # --- logo ---
    assets_dir = Path(__file__).resolve().parent / "ICON"
    logo_path = assets_dir / "td_logo.png"   # <--- put your logo here
    logo_src = _file_to_data_uri(logo_path)

    # --- theme (green TD-like) ---
    theme = gr.themes.Soft(
        primary_hue="green",
        secondary_hue="green",
        neutral_hue="gray",
    )

    # --- css (clean white + green, card layout, nicer spacing) ---
    custom_css = """
    :root{
      --td-green: #0B7E3E;
      --td-green-dark: #075C2D;
      --td-border: #E5E7EB;
      --td-text: #111827;
      --td-subtext: #4B5563;
      --td-bg: #FFFFFF;
      --td-card: #FFFFFF;
    }

    body, .gradio-container {
      background: var(--td-bg) !important;
    }

    /* Hide Gradio footer */
    footer { display: none !important; }

    /* Page width */
    .td-wrap {
      max-width: 1150px;
      margin: 0 auto;
      padding: 18px 14px 10px 14px;
    }

    /* Header */
    .td-header {
      display: flex;
      align-items: center;
      gap: 14px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--td-border);
      margin-bottom: 18px;
    }
    .td-logo img {
      height: 44px;
      width: auto;
      display: block;
    }
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

    /* Cards */
    .td-card {
      border: 1px solid var(--td-border);
      border-radius: 14px;
      background: var(--td-card);
      padding: 14px;
      box-shadow: 0 1px 2px rgba(0,0,0,.05);
    }

    /* Buttons */
    .gr-button-primary,
    button.primary {
      background: var(--td-green) !important;
      border: none !important;
      color: white !important;
      border-radius: 10px !important;
      font-weight: 700 !important;
    }
    .gr-button-primary:hover,
    button.primary:hover {
      background: var(--td-green-dark) !important;
    }

    /* Inputs */
    textarea, input {
      border-radius: 10px !important;
    }

    /* Make outputs feel like “panels” */
    .td-panel .gr-form {
      gap: 10px;
    }
    """

    header_html = f"""
    <div class="td-wrap">
      <div class="td-header">
        <div class="td-logo">
          {"<img src='" + logo_src + "' alt='TD Logo' />" if logo_src else "<div style='font-weight:800;color:#0B7E3E;'>TD</div>"}
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

    with gr.Blocks(theme=theme, css=custom_css, title="AMCB TEXT2SQL") as demo:
        gr.HTML(header_html)

        with gr.Row():
            with gr.Column(scale=5):
                with gr.Group(elem_classes=["td-wrap", "td-card", "td-panel"]):
                    question = gr.Textbox(
                        label="Ask your question",
                        placeholder="Example: Show top 10 accounts by total balance for last month",
                        lines=3,
                    )
                    do_execute = gr.Checkbox(label="Execute SQL", value=True)
                    with gr.Row():
                        run_btn = gr.Button("Run", variant="primary")
                        clear_btn = gr.Button("Clear", variant="secondary")

            with gr.Column(scale=5):
                with gr.Group(elem_classes=["td-wrap", "td-card", "td-panel"]):
                    sql_out = gr.Code(label="Generated SQL", language="sql")
                    result_out = gr.Textbox(label="SQL Result", lines=16, interactive=False)

        run_btn.click(
            fn=lambda q, ex: gradio_ask_question(q, ex, engine, search_client),
            inputs=[question, do_execute],
            outputs=[sql_out, result_out],
        )

        clear_btn.click(
            fn=lambda: ("", "", ""),
            inputs=None,
            outputs=[question, sql_out, result_out],
        )

    demo.launch(inbrowser=True, share=True)
