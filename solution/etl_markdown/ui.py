# app/ui.py
from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

from app.nl2sql import handle_user_turn
from app.config import get_config
from app.ai_search_service import AISearchService
from app.identity import get_search_credential, IdentityError

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore


TD_GREEN = "#008A00"
TD_GREEN_DARK = "#006D00"
TD_BG = "#F6F7F9"
TD_CARD = "#FFFFFF"
TD_TEXT = "#111827"
TD_MUTED = "#6B7280"
TD_BORDER = "#E5E7EB"

CSS = f"""
:root {{
  --td-green: {TD_GREEN};
  --td-green-dark: {TD_GREEN_DARK};
  --td-bg: {TD_BG};
  --td-card: {TD_CARD};
  --td-text: {TD_TEXT};
  --td-muted: {TD_MUTED};
  --td-border: {TD_BORDER};
}}

html, body {{
  background: var(--td-bg) !important;
}}

#td-app {{
  max-width: 1240px;
  margin: 0 auto;
  padding: 18px 14px 28px 14px;
}}

#td-header {{
  background: var(--td-card);
  border: 1px solid var(--td-border);
  border-radius: 14px;
  padding: 14px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 8px 24px rgba(17, 24, 39, 0.06);
  margin-bottom: 14px;
}}

#td-brand {{
  display: flex;
  gap: 12px;
  align-items: center;
}}

#td-logo {{
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: var(--td-green);
  color: white;
  display: grid;
  place-items: center;
  font-weight: 800;
  letter-spacing: 0.5px;
}}

#td-title {{
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}}
#td-title b {{
  font-size: 15px;
  color: var(--td-text);
}}
#td-title span {{
  font-size: 12px;
  color: var(--td-muted);
}}

#td-status {{
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 12px;
  color: var(--td-muted);
}}
.td-pill {{
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--td-border);
  background: #fff;
}}
.td-dot {{
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: #9CA3AF;
}}
.td-dot.ok {{
  background: var(--td-green);
}}

#td-body {{
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 14px;
}}

@media (max-width: 980px) {{
  #td-body {{
    grid-template-columns: 1fr;
  }}
}}

.td-card {{
  background: var(--td-card);
  border: 1px solid var(--td-border);
  border-radius: 14px;
  padding: 14px;
  box-shadow: 0 8px 24px rgba(17, 24, 39, 0.06);
}}

.td-card h3 {{
  margin: 0 0 10px 0;
  font-size: 13px;
  color: var(--td-text);
}}

.td-help {{
  color: var(--td-muted);
  font-size: 12px;
  margin-top: 2px;
}}

.td-divider {{
  height: 1px;
  background: var(--td-border);
  margin: 12px 0;
}}

#chatbox_wrap {{
  min-height: 440px;
}}

#sql_code pre {{
  border-radius: 12px !important;
}}

#grid_wrap {{
  margin-top: 10px;
}}

#grid_wrap table {{
  border-radius: 12px !important;
}}

button.primary, .gr-button-primary {{
  background: var(--td-green) !important;
  border-color: var(--td-green) !important;
}}
button.primary:hover, .gr-button-primary:hover {{
  background: var(--td-green-dark) !important;
  border-color: var(--td-green-dark) !important;
}}

.gr-button-secondary {{
  border-color: var(--td-border) !important;
}}

#tiny_status {{
  font-size: 12px;
  color: var(--td-muted);
}}
"""

HEADER_HTML = f"""
<div id="td-app">
  <div id="td-header">
    <div id="td-brand">
      <div id="td-logo">TD</div>
      <div id="td-title">
        <b>NL → SQL Chatbot</b>
        <span>Azure OpenAI + SQL Server + Azure AI Search metadata</span>
      </div>
    </div>
    <div id="td-status">
      <span class="td-pill"><span class="td-dot ok"></span>SQL</span>
      <span class="td-pill"><span class="td-dot ok"></span>AI Search</span>
    </div>
  </div>
</div>
"""


def _safe_str(x: Any) -> str:
    try:
        return "" if x is None else str(x)
    except Exception:
        return ""


def sanitize_index_name(raw: str) -> str:
    """
    Azure AI Search index name rules (common):
    - lowercase letters, digits, hyphens
    - can't start/end with hyphen
    - <= 128 chars
    """
    s = _safe_str(raw).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:128]


def to_chatbot_messages(app_messages: Any) -> List[Dict[str, str]]:
    """
    Always return Gradio "messages" format:
    [{"role":"user|assistant|system|tool","content":"..."}]
    """
    out: List[Dict[str, str]] = []
    if not app_messages:
        return out

    for m in app_messages:
        role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None) or "assistant"
        content = getattr(m, "content", None) if not isinstance(m, dict) else m.get("content")
        role_s = _safe_str(role).strip().lower() or "assistant"
        content_s = _safe_str(content)

        # Normalize roles for display
        if role_s not in {"user", "assistant", "system", "tool"}:
            role_s = "assistant"

        # Make "tool/system" readable inside chat
        if role_s == "tool":
            content_s = f"[DATA]\n{content_s}"
            role_s = "assistant"
        elif role_s == "system":
            content_s = f"{content_s}"
            role_s = "assistant"

        out.append({"role": role_s, "content": content_s})
    return out


def to_dataframe(value: Any):
    if pd is None:
        return value

    if value is None:
        return pd.DataFrame()

    if hasattr(value, "to_dict") and hasattr(value, "columns"):
        # pandas dataframe-like
        try:
            return value
        except Exception:
            return pd.DataFrame()

    if isinstance(value, list):
        if len(value) == 0:
            return pd.DataFrame()
        if isinstance(value[0], dict):
            return pd.DataFrame(value)
        if isinstance(value[0], (list, tuple)):
            return pd.DataFrame(value)

    if isinstance(value, dict):
        # common shapes: {"columns": [...], "rows": [...]}
        cols = value.get("columns")
        rows = value.get("rows")
        if isinstance(cols, list) and isinstance(rows, list):
            try:
                return pd.DataFrame(rows, columns=cols)
            except Exception:
                return pd.DataFrame(rows)
        # single record
        try:
            return pd.DataFrame([value])
        except Exception:
            return pd.DataFrame()

    # string / scalar
    return pd.DataFrame()


def build_ui() -> gr.Blocks:
    config = get_config()

    ai_service: Optional[AISearchService] = None
    ai_error: Optional[str] = None
    try:
        cred = get_search_credential(config)
        ai_service = AISearchService(config.ai_search_endpoint, cred)
    except IdentityError as e:
        ai_error = f"Azure AI Search identity error: {_safe_str(e)}"
    except Exception as e:
        ai_error = f"Azure AI Search initialization failed: {_safe_str(e)}"

    def safe_list_indexes(timeout_s: int = 10) -> Tuple[bool, Any]:
        """
        Returns (ok, result). result is either list[str] or error string/exception
        """
        if not ai_service:
            return False, (ai_error or "Azure AI Search is not initialized.")
        try:
            fn = getattr(ai_service, "safe_list_indexes", None)
            if callable(fn):
                return fn(timeout_s=timeout_s)
            # fallback
            return True, ai_service.list_indexes()
        except Exception as e:
            return False, e

    def friendly_err(e: Any) -> str:
        msg = _safe_str(e)
        if "multiple user assigned identities exist" in msg.lower():
            return (
                "Multiple user-assigned identities exist. Set AI_SEARCH_MANAGED_IDENTITY_CLIENT_ID "
                "or AZURE_CLIENT_ID."
            )
        if "forbidden" in msg.lower() or "unauthorized" in msg.lower():
            return "Access forbidden/unauthorized. Verify RBAC and identity permissions on the Search service."
        if "timed out" in msg.lower() or "timeout" in msg.lower():
            return "Request timed out. Try again or check network connectivity."
        return msg or "Unknown error"

    def refresh_indexes(current_value: Optional[str], state: Dict[str, Any]):
        ok, result = safe_list_indexes(timeout_s=10)
        if not ok:
            status = f"❌ {friendly_err(result)}"
            # keep existing choices/value
            return (
                gr.update(),
                gr.update(),
                gr.update(value=status, visible=True),
                gr.update(value=status, visible=True),
                state,
            )

        choices = [c for c in (result or []) if isinstance(c, str)]
        # Preserve current if still valid, else fallback to config/default
        candidate = _safe_str(current_value).strip()
        if candidate and candidate in choices:
            selected = candidate
        else:
            cfg_default = _safe_str(getattr(config, "ai_search_index", "")).strip()
            env_default = _safe_str(os.getenv("AI_SEARCH_DEFAULT_INDEX", "")).strip()
            selected = cfg_default if cfg_default in choices else (env_default if env_default in choices else (choices[0] if choices else None))

        # update shared state too
        state = dict(state or {})
        state["selected_index"] = selected

        status = f"✅ Refreshed {len(choices)} index(es)." if choices else "⚠️ No indexes found."
        return (
            gr.update(choices=choices, value=selected),
            gr.update(choices=choices, value=selected),
            gr.update(value=status, visible=True),
            gr.update(value=status, visible=True),
            state,
        )

    def sync_index_from_chat(idx: Optional[str], state: Dict[str, Any]):
        state = dict(state or {})
        state["selected_index"] = idx
        return gr.update(value=idx), state

    def sync_index_from_search(idx: Optional[str], state: Dict[str, Any]):
        state = dict(state or {})
        state["selected_index"] = idx
        return gr.update(value=idx), state

    def do_turn(user_text: str, state: Dict[str, Any], selected_index: Optional[str]):
        state = dict(state or {})
        messages = state.get("messages") or []
        pending_sql = state.get("pending_sql") or ""

        # store chosen index for downstream retrieval / context
        try:
            setattr(config, "selected_index", selected_index)
        except Exception:
            pass

        try:
            new_messages, new_pending_sql, last_sql, last_result_compact = handle_user_turn(
                user_text, messages, pending_sql, config
            )
        except TypeError:
            # fallback if signature differs
            new_messages, new_pending_sql, last_sql, last_result_compact = handle_user_turn(
                user_text, messages, pending_sql
            )

        state["messages"] = new_messages
        state["pending_sql"] = new_pending_sql
        state["last_sql"] = last_sql or ""
        state["last_result_compact"] = last_result_compact
        state["selected_index"] = selected_index

        chat_val = to_chatbot_messages(new_messages)
        sql_val = state["last_sql"]
        df_val = to_dataframe(last_result_compact)

        return chat_val, state, "", sql_val, df_val

    def list_tables(state: Dict[str, Any], selected_index: Optional[str]):
        return do_turn("list tables", state, selected_index)

    def reset_all():
        fresh = {
            "messages": [],
            "pending_sql": "",
            "last_sql": "",
            "last_result_compact": None,
            "selected_index": None,
        }
        empty_df = pd.DataFrame() if pd is not None else []
        return [], fresh, "", "", empty_df

    # Azure AI Search actions
    def create_index(new_name: str, state: Dict[str, Any]):
        if not ai_service:
            status = f"❌ {ai_error or 'Azure AI Search is not initialized.'}"
            return gr.update(), gr.update(), status, status, state

        idx = sanitize_index_name(new_name)
        if not idx:
            status = "❌ Invalid index name. Use letters/digits/hyphens (we auto-sanitize)."
            return gr.update(), gr.update(), status, status, state

        try:
            fn = getattr(ai_service, "create_metadata_index", None) or getattr(ai_service, "create_index", None)
            if not callable(fn):
                raise RuntimeError("AISearchService has no create_metadata_index/create_index method.")
            ok, msg = fn(idx) if fn.__code__.co_argcount == 2 else fn(index_name=idx)  # type: ignore
            if not ok:
                status = f"❌ {friendly_err(msg)}"
                return gr.update(), gr.update(), status, status, state
        except Exception as e:
            status = f"❌ {friendly_err(e)}"
            return gr.update(), gr.update(), status, status, state

        # refresh indexes after creation
        chat_dd, search_dd, chat_status, search_status, state = refresh_indexes(idx, state)
        created = f"✅ Created index: `{idx}`"
        return chat_dd, search_dd, created, created, state

    def upload_metadata(file_obj: Any, selected_index: Optional[str]):
        if not ai_service:
            return f"❌ {ai_error or 'Azure AI Search is not initialized.'}", ""

        idx = _safe_str(selected_index).strip()
        if not idx:
            return "❌ Please select an index first.", ""

        # Resolve file path from Gradio File
        path = None
        if isinstance(file_obj, str):
            path = file_obj
        else:
            path = getattr(file_obj, "name", None) or getattr(file_obj, "path", None)
        path = _safe_str(path).strip()

        if not path:
            return "❌ No file selected.", ""

        try:
            fn = getattr(ai_service, "ingest_pipe_file", None) or getattr(ai_service, "ingest_file", None)
            if not callable(fn):
                raise RuntimeError("AISearchService has no ingest_pipe_file/ingest_file method.")
            success, fail, msg = fn(idx, path)
            base = f"✅ Uploaded. Success={success}, Fail={fail}." if (success or fail) else f"✅ Uploaded. {msg}"
        except Exception as e:
            return f"❌ {friendly_err(e)}", ""

        # Try stats
        stats_msg = ""
        try:
            stats_fn = getattr(ai_service, "get_index_stats", None)
            if callable(stats_fn):
                stats = stats_fn(idx)
                if isinstance(stats, dict):
                    doc_count = stats.get("document_count", stats.get("documentCount", "N/A"))
                    stats_msg = f"📈 Document count: **{doc_count}**"
        except Exception:
            stats_msg = ""

        return base, stats_msg

    with gr.Blocks(title="NL→SQL Chatbot") as demo:
        gr.HTML(f"<style>{CSS}</style>")
        gr.HTML(HEADER_HTML)

        # shared app state
        state = gr.State(
            {
                "messages": [],
                "pending_sql": "",
                "last_sql": "",
                "last_result_compact": None,
                "selected_index": None,
            }
        )

        with gr.Row(elem_id="td-body"):
            # LEFT SIDEBAR
            with gr.Column(elem_classes=["td-card"]):
                gr.Markdown("### Context")
                gr.Markdown("Choose the Azure AI Search index used as metadata reference.", elem_classes=["td-help"])

                chat_refresh_btn = gr.Button("Refresh Index List", variant="primary")
                chat_refresh_status = gr.Markdown("", elem_id="tiny_status", visible=False)

                chat_index_dd = gr.Dropdown(
                    label="Metadata Index (used by Chat)",
                    choices=[],
                    value=None,
                )

                list_tables_btn = gr.Button("List Tables", variant="secondary")

                gr.Markdown("### Generated SQL")
                sql_code = gr.Code(label="SQL", value="", language="sql", elem_id="sql_code")

                gr.Markdown("### Results (Grid)")
                results_grid = gr.Dataframe(
                    value=pd.DataFrame() if pd is not None else [],
                    interactive=False,
                    elem_id="grid_wrap",
                    label="Grid view",
                )

            # RIGHT MAIN AREA
            with gr.Column():
                with gr.Tabs():
                    with gr.Tab("Chat"):
                        with gr.Column(elem_classes=["td-card"], elem_id="chatbox_wrap"):
                            chatbot = gr.Chatbot(label="Chat", value=[])
                            user_input = gr.Textbox(
                                label="Textbox",
                                placeholder="Ask a question about your data...",
                            )
                            with gr.Row():
                                send_btn = gr.Button("Send", variant="primary")
                                clear_btn = gr.Button("Clear", variant="secondary")

                    with gr.Tab("Azure AI Search"):
                        with gr.Column(elem_classes=["td-card"]):
                            gr.Markdown("### Connection")
                            endpoint = _safe_str(getattr(config, "ai_search_endpoint", "")).strip()
                            gr.Markdown(f"**Endpoint:** {endpoint or '(not set)'}")

                            search_refresh_btn = gr.Button("List Indexes / Refresh", variant="primary")
                            search_refresh_status = gr.Markdown("", elem_id="tiny_status", visible=False)

                            search_index_dd = gr.Dropdown(
                                label="Select Index",
                                choices=[],
                                value=None,
                            )

                            gr.Markdown("### Create Index")
                            new_index_name = gr.Textbox(
                                label="New Index Name",
                                placeholder="example: edc-metadata",
                            )
                            create_index_btn = gr.Button("Create Index", variant="secondary")

                            gr.Markdown("### Upload metadata (pipe-separated)")
                            upload_file = gr.File(label="Upload Metadata File (.txt/.psv/.csv)")
                            upload_btn = gr.Button("Upload to Selected Index", variant="secondary")
                            upload_status = gr.Markdown("")
                            upload_stats = gr.Markdown("")

        # --- Wire events (no render(), no duplicate blocks) ---

        # Refresh indexes (updates BOTH dropdowns + BOTH statuses + state)
        chat_refresh_btn.click(
            refresh_indexes,
            inputs=[chat_index_dd, state],
            outputs=[chat_index_dd, search_index_dd, chat_refresh_status, search_refresh_status, state],
        )
        search_refresh_btn.click(
            refresh_indexes,
            inputs=[search_index_dd, state],
            outputs=[chat_index_dd, search_index_dd, chat_refresh_status, search_refresh_status, state],
        )

        # Sync dropdown selections across tabs
        chat_index_dd.change(
            sync_index_from_chat,
            inputs=[chat_index_dd, state],
            outputs=[search_index_dd, state],
        )
        search_index_dd.change(
            sync_index_from_search,
            inputs=[search_index_dd, state],
            outputs=[chat_index_dd, state],
        )

        # Chat turn
        send_btn.click(
            do_turn,
            inputs=[user_input, state, chat_index_dd],
            outputs=[chatbot, state, user_input, sql_code, results_grid],
        )
        user_input.submit(
            do_turn,
            inputs=[user_input, state, chat_index_dd],
            outputs=[chatbot, state, user_input, sql_code, results_grid],
        )

        # List tables shortcut
        list_tables_btn.click(
            list_tables,
            inputs=[state, chat_index_dd],
            outputs=[chatbot, state, user_input, sql_code, results_grid],
        )

        # Clear
        clear_btn.click(
            reset_all,
            inputs=[],
            outputs=[chatbot, state, user_input, sql_code, results_grid],
        )

        # Azure AI Search: create index (refreshes both dropdowns + statuses)
        create_index_btn.click(
            create_index,
            inputs=[new_index_name, state],
            outputs=[chat_index_dd, search_index_dd, chat_refresh_status, search_refresh_status, state],
        )

        # Azure AI Search: upload file
        upload_btn.click(
            upload_metadata,
            inputs=[upload_file, search_index_dd],
            outputs=[upload_status, upload_stats],
        )

        # Initial refresh on load (safe)
        demo.load(
            refresh_indexes,
            inputs=[chat_index_dd, state],
            outputs=[chat_index_dd, search_index_dd, chat_refresh_status, search_refresh_status, state],
        )

    return demo
