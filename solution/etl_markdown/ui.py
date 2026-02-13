# app/ui.py
from __future__ import annotations

import inspect
import os
import re
import traceback
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

from app.nl2sql import handle_user_turn
from app.config import get_config
from app.ai_search_service import AISearchService
from app.identity import get_search_credential, IdentityError


# -----------------------------
# Styling (TD-like: clean + green)
# -----------------------------
CSS = r"""
:root{
  --td-green:#00A651;
  --td-green-dark:#008A43;
  --bg:#F6F7F8;
  --card:#FFFFFF;
  --muted:#6B7280;
  --text:#111827;
  --border:#E5E7EB;
  --shadow:0 8px 24px rgba(17,24,39,.08);
  --radius:14px;
}

body, .gradio-container{
  background: var(--bg) !important;
  color: var(--text) !important;
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji" !important;
}

.gradio-container .wrap{ max-width: 1200px !important; }

/* Header */
#topbar{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 14px 16px;
  margin-bottom: 14px;
}
#topbar .brand{
  display:flex; align-items:center; gap:10px;
}
#topbar .logo{
  width:38px; height:38px; border-radius:12px;
  background: linear-gradient(145deg, var(--td-green), var(--td-green-dark));
  display:flex; align-items:center; justify-content:center;
  color:#fff; font-weight:800; letter-spacing:.5px;
}
#topbar .title{
  font-size:18px; font-weight:800; margin:0; line-height:1.1;
}
#topbar .subtitle{
  margin:0; color:var(--muted); font-size:12.5px;
}
#topbar .right{
  display:flex; align-items:center; gap:10px; justify-content:flex-end;
}
.badge{
  display:inline-flex; align-items:center; gap:8px;
  padding:7px 10px;
  border-radius:999px;
  border:1px solid var(--border);
  background:#fff;
  font-size:12px;
  color:var(--muted);
}
.badge .dot{
  width:10px; height:10px; border-radius:50%;
  background:#D1D5DB;
}
.badge.ok .dot{ background: var(--td-green); }
.badge.err .dot{ background:#EF4444; }

/* Cards */
.card{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 14px;
}
.card h3{
  margin:0 0 10px 0;
  font-size:13px;
  letter-spacing:.2px;
  color: var(--text);
}
.hint{ color:var(--muted); font-size:12px; margin-top:6px; }

/* Buttons */
.gr-button, button{
  border-radius: 12px !important;
  border: 1px solid var(--border) !important;
  box-shadow: none !important;
}
.gr-button.primary, button.primary{
  background: var(--td-green) !important;
  border-color: var(--td-green) !important;
  color: #fff !important;
  font-weight: 700 !important;
}
.gr-button.primary:hover, button.primary:hover{
  background: var(--td-green-dark) !important;
  border-color: var(--td-green-dark) !important;
}

/* Inputs */
textarea, input, .gr-text-input{
  border-radius: 12px !important;
}
.gr-input, .gr-dropdown, .gr-textbox, .gr-code, .gr-file{
  border-radius: 12px !important;
}

/* Tabs */
.gr-tabitem{
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  background: var(--card) !important;
  box-shadow: var(--shadow) !important;
  padding: 12px !important;
}

/* Chat */
#chatbox{
  min-height: 520px;
  border-radius: var(--radius);
}
#sql_code pre, #sql_code textarea{
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono","Courier New", monospace !important;
  font-size: 12px !important;
}
#results_grid{
  border-radius: var(--radius);
  overflow:hidden;
}

/* Sticky-ish left column */
@media (min-width: 980px){
  #leftcol{
    position: sticky;
    top: 14px;
    align-self: flex-start;
  }
}
"""


# -----------------------------
# Helpers
# -----------------------------
def _safe_str(x: Any) -> str:
    try:
        return "" if x is None else str(x)
    except Exception:
        return "<unprintable>"


def _sanitize_index_name(name: str) -> str:
    name = (name or "").strip().lower()
    name = re.sub(r"[\s_]+", "-", name)
    name = re.sub(r"[^a-z0-9-]", "", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name[:128]


def _make_badge_html(ai_ok: bool, sql_ok: bool) -> str:
    ai_cls = "badge ok" if ai_ok else "badge err"
    sql_cls = "badge ok" if sql_ok else "badge err"
    return f"""
<div id="topbar">
  <div style="display:flex; align-items:center; justify-content:space-between; gap:12px;">
    <div class="brand">
      <div class="logo">TD</div>
      <div>
        <p class="title">NL → SQL Chatbot</p>
        <p class="subtitle">Azure OpenAI + SQL Server + Azure AI Search metadata</p>
      </div>
    </div>
    <div class="right">
      <span class="{sql_cls}"><span class="dot"></span>SQL</span>
      <span class="{ai_cls}"><span class="dot"></span>AI Search</span>
    </div>
  </div>
</div>
"""


def _chatbot_supports_type_param() -> bool:
    try:
        return "type" in inspect.signature(gr.Chatbot).parameters
    except Exception:
        return False


def _make_chatbot(label: str, elem_id: str):
    """
    Fixes your current Gradio error:
    - Some Gradio versions default Chatbot to messages format (list[dict]).
    - We always output tuple format: list[tuple(user, assistant)].
    - So if supported, force type='tuples'.
    """
    kwargs: Dict[str, Any] = {"label": label, "elem_id": elem_id}
    if _chatbot_supports_type_param():
        kwargs["type"] = "tuples"
    return gr.Chatbot(**kwargs)


def _to_chat_pairs(app_messages: Any) -> List[Tuple[str, str]]:
    """
    Convert internal messages -> List[Tuple[user, assistant]]
    """
    pairs: List[Tuple[str, str]] = []
    last_user: Optional[str] = None

    if not app_messages:
        return pairs

    for m in app_messages:
        role = None
        content = None

        if hasattr(m, "role") and hasattr(m, "content"):
            role = getattr(m, "role", None)
            content = getattr(m, "content", None)
        elif isinstance(m, dict):
            role = m.get("role")
            content = m.get("content")
        else:
            role = "assistant"
            content = _safe_str(m)

        role = _safe_str(role).lower().strip()
        content_s = _safe_str(content)

        if role == "user":
            if last_user is not None:
                pairs.append((last_user, ""))
            last_user = content_s
        else:
            # assistant/system/tool/unknown -> show as assistant bubble
            if last_user is None:
                pairs.append(("", content_s))
            else:
                pairs.append((last_user, content_s))
                last_user = None

    if last_user is not None:
        pairs.append((last_user, ""))

    return pairs


def _try_import_pandas():
    try:
        import pandas as pd  # type: ignore
        return pd
    except Exception:
        return None


def _result_to_grid(result: Any):
    pd = _try_import_pandas()
    if result is None:
        return []

    if pd is not None:
        try:
            if isinstance(result, pd.DataFrame):
                return result
        except Exception:
            pass

    if isinstance(result, list) and result and isinstance(result[0], dict):
        if pd is not None:
            try:
                return pd.DataFrame(result)
            except Exception:
                return result
        return result

    if isinstance(result, dict):
        cols = result.get("columns") or result.get("cols") or result.get("headers")
        rows = result.get("rows") or result.get("data")
        if cols is not None and rows is not None:
            if pd is not None:
                try:
                    return pd.DataFrame(rows, columns=cols)
                except Exception:
                    pass
            return rows

    if isinstance(result, list):
        return result

    return []


def _safe_call_handle_user_turn(user_text: str, messages: Any, pending_sql: str, config: Any):
    """
    Expected output: (new_messages, new_pending_sql, last_sql, last_result_compact)
    """
    sig = inspect.signature(handle_user_turn)
    params = sig.parameters
    kwargs: Dict[str, Any] = {}

    if "user_text" in params:
        kwargs["user_text"] = user_text
    elif "prompt" in params:
        kwargs["prompt"] = user_text

    if "messages" in params:
        kwargs["messages"] = messages
    elif "app_messages" in params:
        kwargs["app_messages"] = messages

    if "pending_sql" in params:
        kwargs["pending_sql"] = pending_sql

    if "config" in params:
        kwargs["config"] = config

    if kwargs:
        out = handle_user_turn(**kwargs)
    else:
        out = handle_user_turn(user_text, messages, pending_sql, config)

    if isinstance(out, tuple) and len(out) == 4:
        return out
    raise RuntimeError(f"handle_user_turn returned unexpected value: {_safe_str(out)[:200]}")


def _make_dataframe_component(label: str, elem_id: str):
    try:
        return gr.Dataframe(value=[], label=label, interactive=False, elem_id=elem_id)
    except Exception:
        try:
            return gr.Dataframe(value=[], label=label, elem_id=elem_id)
        except Exception:
            return gr.Dataframe(label=label, elem_id=elem_id)


# -----------------------------
# UI
# -----------------------------
def build_ui() -> gr.Blocks:
    config = None
    ai_service = None
    init_error = None

    try:
        config = get_config()
        try:
            credential = get_search_credential(config)
            ai_service = AISearchService(config.ai_search_endpoint, credential)
        except IdentityError as e:
            init_error = f"AI Search identity error: {_safe_str(e)}"
        except Exception as e:
            init_error = f"AI Search initialization failed: {_safe_str(e)}"
    except Exception as e:
        init_error = f"Config initialization failed: {_safe_str(e)}"

    index_choices: List[str] = []
    default_index: Optional[str] = None

    if ai_service is not None:
        try:
            index_choices = list(ai_service.list_indexes() or [])
        except Exception:
            index_choices = []

    if config is not None:
        cfg_default = getattr(config, "ai_search_default_index", None) or getattr(config, "ai_search_index", None)
        if cfg_default and cfg_default in index_choices:
            default_index = cfg_default

    if default_index is None and index_choices:
        default_index = index_choices[0]

    ai_ok = ai_service is not None
    sql_ok = True
    header_html = _make_badge_html(ai_ok=ai_ok, sql_ok=sql_ok)

    with gr.Blocks(css=CSS) as demo:
        gr.HTML(value=header_html)

        state = gr.State(
            {
                "messages": [],
                "pending_sql": "",
                "last_sql": "",
                "last_result_compact": None,
                "selected_index": default_index,
            }
        )

        if init_error:
            gr.Markdown(
                f"""
<div class="card" style="border-color:#FCA5A5;">
  <h3 style="color:#991B1B;">Startup error</h3>
  <div style="color:#7F1D1D; font-size:12.5px; white-space:pre-wrap;">{init_error}</div>
</div>
""".strip()
            )

        with gr.Tabs():
            # -------------------------
            # Chat Tab
            # -------------------------
            with gr.Tab("Chat"):
                with gr.Row():
                    with gr.Column(scale=4, elem_id="leftcol"):
                        with gr.Group(elem_classes=["card"]):
                            gr.Markdown("### Context")
                            gr.Markdown(
                                "Choose the Azure AI Search index used as metadata reference.",
                                elem_classes=["hint"],
                            )
                            refresh_btn = gr.Button("Refresh Index List", variant="primary")
                            index_dd = gr.Dropdown(
                                label="Metadata Index (used by Chat)",
                                choices=index_choices,
                                value=default_index if default_index in index_choices else None,
                            )
                            refresh_status = gr.Markdown(value="", visible=False)
                            list_tables_btn = gr.Button("List Tables")

                        with gr.Group(elem_classes=["card"]):
                            gr.Markdown("### Generated SQL")
                            sql_code = gr.Code(value="", language="sql", elem_id="sql_code")

                        with gr.Group(elem_classes=["card"]):
                            gr.Markdown("### Results (Grid)")
                            results_grid = _make_dataframe_component("Grid view", elem_id="results_grid")
                            raw_debug = gr.Markdown(value="", visible=False)

                    with gr.Column(scale=8):
                        # IMPORTANT FIX: force tuples mode when supported
                        chatbot = _make_chatbot(label="Chat", elem_id="chatbox")
                        user_input = gr.Textbox(
                            placeholder="Ask a question about your data…",
                            label="",
                            lines=2,
                        )
                        with gr.Row():
                            send_btn = gr.Button("Send", variant="primary")
                            clear_btn = gr.Button("Clear")

                def _set_selected_index(idx: Optional[str], st: Dict[str, Any]):
                    st = dict(st or {})
                    st["selected_index"] = idx
                    return st

                def _refresh_indexes(current_value: Optional[str], st: Dict[str, Any]):
                    try:
                        if ai_service is None:
                            st = _set_selected_index(current_value, st)
                            return (
                                gr.update(),
                                gr.update(visible=True, value="❌ AI Search service not available."),
                                st,
                            )

                        choices = list(ai_service.list_indexes() or [])
                        selected = current_value if current_value in choices else (choices[0] if choices else None)
                        st = _set_selected_index(selected, st)
                        return (
                            gr.update(choices=choices, value=selected),
                            gr.update(visible=True, value=f"✅ Refreshed {len(choices)} index(es)."),
                            st,
                        )
                    except Exception as e:
                        st = _set_selected_index(current_value, st)
                        return (
                            gr.update(),
                            gr.update(visible=True, value=f"❌ Refresh failed: {_safe_str(e)}"),
                            st,
                        )

                def _send(user_text: str, st: Dict[str, Any], selected_index: Optional[str]):
                    st = dict(st or {})
                    messages = st.get("messages", [])
                    pending_sql = st.get("pending_sql", "")

                    if config is not None and hasattr(config, "selected_index"):
                        try:
                            setattr(config, "selected_index", selected_index)
                        except Exception:
                            pass

                    try:
                        new_messages, new_pending_sql, last_sql, last_result_compact = _safe_call_handle_user_turn(
                            user_text=user_text,
                            messages=messages,
                            pending_sql=pending_sql,
                            config=config,
                        )

                        st["messages"] = new_messages
                        st["pending_sql"] = new_pending_sql
                        st["last_sql"] = last_sql
                        st["last_result_compact"] = last_result_compact
                        st["selected_index"] = selected_index

                        chat_pairs = _to_chat_pairs(new_messages)
                        grid_val = _result_to_grid(last_result_compact)

                        raw = ""
                        if last_result_compact is not None and not isinstance(last_result_compact, (list, dict)):
                            raw = _safe_str(last_result_compact)

                        return (
                            chat_pairs,
                            st,
                            "",
                            last_sql or "",
                            grid_val,
                            gr.update(visible=bool(raw), value=f"```text\n{raw}\n```" if raw else ""),
                        )
                    except Exception as e:
                        tb = traceback.format_exc()
                        chat_pairs = _to_chat_pairs(messages)
                        chat_pairs.append(("", f"❌ Error: {_safe_str(e)}"))
                        return (
                            chat_pairs,
                            st,
                            user_text,
                            st.get("last_sql", "") or "",
                            _result_to_grid(st.get("last_result_compact")),
                            gr.update(visible=True, value=f"```text\n{tb}\n```"),
                        )

                def _list_tables(st: Dict[str, Any], selected_index: Optional[str]):
                    return _send("list tables", st, selected_index)

                def _clear():
                    empty_state = {
                        "messages": [],
                        "pending_sql": "",
                        "last_sql": "",
                        "last_result_compact": None,
                        "selected_index": default_index,
                    }
                    return (
                        [],
                        empty_state,
                        "",
                        "",
                        [],
                        gr.update(visible=False, value=""),
                    )

                refresh_btn.click(
                    _refresh_indexes,
                    inputs=[index_dd, state],
                    outputs=[index_dd, refresh_status, state],
                )

                index_dd.change(
                    lambda idx, st: _set_selected_index(idx, st),
                    inputs=[index_dd, state],
                    outputs=[state],
                )

                send_btn.click(
                    _send,
                    inputs=[user_input, state, index_dd],
                    outputs=[chatbot, state, user_input, sql_code, results_grid, raw_debug],
                )
                user_input.submit(
                    _send,
                    inputs=[user_input, state, index_dd],
                    outputs=[chatbot, state, user_input, sql_code, results_grid, raw_debug],
                )
                list_tables_btn.click(
                    _list_tables,
                    inputs=[state, index_dd],
                    outputs=[chatbot, state, user_input, sql_code, results_grid, raw_debug],
                )
                clear_btn.click(
                    _clear,
                    inputs=[],
                    outputs=[chatbot, state, user_input, sql_code, results_grid, raw_debug],
                )

            # -------------------------
            # Azure AI Search Tab
            # -------------------------
            with gr.Tab("Azure AI Search"):
                with gr.Row():
                    with gr.Column(scale=1):
                        with gr.Group(elem_classes=["card"]):
                            endpoint = ""
                            if config is not None:
                                endpoint = getattr(config, "ai_search_endpoint", "") or ""
                            gr.Markdown("### Connection")
                            gr.Markdown(f"**Endpoint:** {endpoint or '(not set)'}")
                            ai_refresh_btn = gr.Button("Refresh", variant="primary")
                            ai_status = gr.Markdown(value="", visible=False)

                        with gr.Group(elem_classes=["card"]):
                            gr.Markdown("### Manage Index")
                            new_index_name = gr.Textbox(
                                label="New Index Name",
                                placeholder="example: edc-metadata",
                            )
                            create_index_btn = gr.Button("Create Index", variant="primary")

                        with gr.Group(elem_classes=["card"]):
                            gr.Markdown("### Upload metadata (pipe-separated)")
                            file_upload = gr.File(label="Upload Metadata File (.txt/.psv/.csv)")
                            upload_btn = gr.Button("Upload to Selected Index", variant="primary")
                            stats_md = gr.Markdown(value="", visible=False)

                    with gr.Column(scale=2):
                        with gr.Group(elem_classes=["card"]):
                            gr.Markdown("### Selected Index")
                            gr.Markdown(
                                "This uses the same **Metadata Index** selected in the **Chat** tab.",
                                elem_classes=["hint"],
                            )
                            selected_idx_view = gr.Textbox(
                                label="Selected Index",
                                value=default_index or "",
                                interactive=False,
                            )
                            index_dd.change(
                                lambda idx: gr.update(value=idx or ""),
                                inputs=[index_dd],
                                outputs=[selected_idx_view],
                            )

                def _ai_refresh(current_value: Optional[str], st: Dict[str, Any]):
                    dd_upd, status_upd, st2 = _refresh_indexes(current_value, st)
                    return dd_upd, status_upd, st2, gr.update(value=(st2.get("selected_index") or ""))

                def _create_index(name: str, current_value: Optional[str], st: Dict[str, Any]):
                    st = dict(st or {})
                    if ai_service is None:
                        return (
                            gr.update(),
                            gr.update(visible=True, value="❌ AI Search service not available."),
                            st,
                            gr.update(value=st.get("selected_index") or ""),
                        )

                    sanitized = _sanitize_index_name(name)
                    if not sanitized:
                        return (
                            gr.update(),
                            gr.update(visible=True, value="❌ Invalid index name. Use letters/digits/dashes."),
                            st,
                            gr.update(value=st.get("selected_index") or ""),
                        )

                    try:
                        ok, msg = ai_service.create_metadata_index(sanitized)
                        choices = list(ai_service.list_indexes() or [])
                        selected = sanitized if sanitized in choices else (
                            current_value if current_value in choices else (choices[0] if choices else None)
                        )
                        st["selected_index"] = selected
                        status = f"{'✅' if ok else '❌'} {msg}"
                        return (
                            gr.update(choices=choices, value=selected),
                            gr.update(visible=True, value=status),
                            st,
                            gr.update(value=(selected or "")),
                        )
                    except Exception as e:
                        return (
                            gr.update(),
                            gr.update(visible=True, value=f"❌ Create failed: {_safe_str(e)}"),
                            st,
                            gr.update(value=st.get("selected_index") or ""),
                        )

                def _upload(file_obj: Any, selected_index: Optional[str]):
                    if ai_service is None:
                        return gr.update(visible=True, value="❌ AI Search service not available."), gr.update(visible=False, value="")

                    if not selected_index:
                        return gr.update(visible=True, value="❌ No selected index."), gr.update(visible=False, value="")

                    if not file_obj:
                        return gr.update(visible=True, value="❌ No file selected."), gr.update(visible=False, value="")

                    try:
                        file_path = getattr(file_obj, "name", None) or getattr(file_obj, "path", None) or None
                        if not file_path:
                            return gr.update(visible=True, value="❌ Could not read uploaded file path."), gr.update(visible=False, value="")

                        success, fail, msg = ai_service.ingest_pipe_file(selected_index, file_path)

                        stats_val = ""
                        try:
                            stats = ai_service.get_index_stats(selected_index)
                            if isinstance(stats, dict):
                                dc = stats.get("document_count", "N/A")
                                ss = stats.get("storage_size", "N/A")
                                stats_val = f"**Documents:** {dc}  \n**Storage:** {ss}"
                        except Exception:
                            stats_val = ""

                        up_msg = f"✅ Uploaded. success={success}, fail={fail}. {msg}"
                        return gr.update(visible=True, value=up_msg), gr.update(visible=bool(stats_val), value=stats_val)
                    except Exception as e:
                        tb = traceback.format_exc()
                        return (
                            gr.update(visible=True, value=f"❌ Upload failed: {_safe_str(e)}"),
                            gr.update(visible=True, value=f"```text\n{tb}\n```"),
                        )

                ai_refresh_btn.click(
                    _ai_refresh,
                    inputs=[index_dd, state],
                    outputs=[index_dd, ai_status, state, selected_idx_view],
                )

                create_index_btn.click(
                    _create_index,
                    inputs=[new_index_name, index_dd, state],
                    outputs=[index_dd, ai_status, state, selected_idx_view],
                )

                upload_btn.click(
                    _upload,
                    inputs=[file_upload, index_dd],
                    outputs=[ai_status, stats_md],
                )

    return demo
