# app/ui.py
from __future__ import annotations

import inspect
import html
import os
from typing import Any, Dict, List, Tuple

import gradio as gr

from app.nl2sql import handle_user_turn
from app.config import get_config
from app.ai_search_service import AISearchService
from app.identity import get_search_credential, IdentityError


# -----------------------------
# TD-like styling (white + green)
# -----------------------------
CSS = r"""
:root{
  --td-green:#008A00;
  --td-green-dark:#006B00;
  --td-bg:#F5F7F6;
  --td-card:#FFFFFF;
  --td-border:#E5E7EB;
  --td-text:#111827;
  --td-muted:#6B7280;
  --td-radius:14px;
  --td-shadow:0 2px 14px rgba(0,0,0,.06);
}

body, .gradio-container{
  background: var(--td-bg) !important;
  color: var(--td-text) !important;
}

#td-header{
  background: var(--td-card);
  border: 1px solid var(--td-border);
  border-radius: var(--td-radius);
  box-shadow: var(--td-shadow);
  padding: 14px 16px;
  margin-bottom: 12px;
}

#td-brand{
  display:flex;
  align-items:center;
  gap:10px;
}

#td-logo{
  width:34px;height:34px;
  border-radius:10px;
  background: var(--td-green);
  display:flex;align-items:center;justify-content:center;
  color:#fff;font-weight:800;
  letter-spacing:.5px;
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
}

#td-title{
  display:flex;
  flex-direction:column;
  line-height:1.1;
}
#td-title h1{
  margin:0;
  font-size:16px;
  font-weight:800;
}
#td-title div{
  margin-top:2px;
  font-size:12px;
  color: var(--td-muted);
}

#td-pills{
  display:flex;
  gap:8px;
  justify-content:flex-end;
  align-items:center;
}

.td-pill{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--td-border);
  background: #fff;
  font-size:12px;
  color: var(--td-text);
  white-space:nowrap;
}
.td-dot{
  width:10px;height:10px;border-radius:99px;background:#9CA3AF;
}
.td-dot.ok{ background: var(--td-green); }
.td-dot.bad{ background: #DC2626; }

.td-card{
  background: var(--td-card);
  border: 1px solid var(--td-border);
  border-radius: var(--td-radius);
  box-shadow: var(--td-shadow);
  padding: 12px 12px;
}

.td-section-title{
  margin:0 0 10px 0;
  font-size:13px;
  font-weight:800;
}

.td-help{
  font-size:12px;
  color: var(--td-muted);
  margin: 0 0 10px 0;
}

#chat-wrap{
  height: 58vh;
  overflow: hidden;
  display:flex;
  flex-direction:column;
}

#chatbot{
  flex:1;
  overflow:auto;
  border: 1px solid var(--td-border);
  border-radius: var(--td-radius);
  background: #fff;
}

#results-wrap{
  height: 26vh;
  overflow:hidden;
  display:flex;
  flex-direction:column;
}

#results-grid{
  flex:1;
  overflow:auto;
  border: 1px solid var(--td-border);
  border-radius: var(--td-radius);
  background:#fff;
  padding: 8px;
}

#sql-code pre, #sql-code code{
  border-radius: 12px !important;
}

button.primary, #send-btn button, #refresh-btn button{
  background: var(--td-green) !important;
  border: 1px solid var(--td-green) !important;
  color: #fff !important;
  font-weight: 800 !important;
  border-radius: 12px !important;
}
button.primary:hover, #send-btn button:hover, #refresh-btn button:hover{
  background: var(--td-green-dark) !important;
  border-color: var(--td-green-dark) !important;
}

#clear-btn button{
  background: #fff !important;
  border: 1px solid var(--td-border) !important;
  color: var(--td-text) !important;
  font-weight: 800 !important;
  border-radius: 12px !important;
}
#clear-btn button:hover{
  border-color: #D1D5DB !important;
}

.td-small{
  font-size:12px;
  color: var(--td-muted);
}

.td-table{
  width:100%;
  border-collapse: collapse;
  font-size:12px;
}
.td-table th{
  position: sticky;
  top: 0;
  background: #F9FAFB;
  z-index: 1;
  text-align:left;
  padding: 8px;
  border-bottom: 1px solid var(--td-border);
  color: #374151;
  font-weight: 800;
}
.td-table td{
  padding: 8px;
  border-bottom: 1px solid var(--td-border);
  vertical-align: top;
}
.td-table tr:hover td{
  background: #F9FAFB;
}
"""


def _safe_str(x: Any) -> str:
  try:
    return "" if x is None else str(x)
  except Exception:
    return repr(x)


def _as_state(d: Any) -> Dict[str, Any]:
  if isinstance(d, dict):
    return d
  return {}


def _render_table_html(result: Any, max_rows: int = 250) -> str:
  """
  Renders common result shapes into a nice HTML grid:
    - list[dict]
    - dict
    - list[list] / list[tuple]
    - string (shown as <pre>)
  """
  if result is None:
    return '<div class="td-small">No results yet.</div>'

  # If someone returned a dict with known keys
  if isinstance(result, dict):
    # common patterns: {"rows": [...], "columns":[...]} or {"data":[...]}
    rows = result.get("rows") or result.get("data")
    cols = result.get("columns") or result.get("cols")
    if isinstance(rows, list):
      return _render_table_html({"columns": cols, "rows": rows}, max_rows=max_rows)

    # otherwise show JSON-ish
    escaped = html.escape(_safe_str(result))
    return f"<pre style='white-space:pre-wrap;margin:0'>{escaped}</pre>"

  # list of dicts
  if isinstance(result, list) and result and isinstance(result[0], dict):
    # union of keys, keep stable order if possible
    keys: List[str] = []
    seen = set()
    for row in result:
      for k in row.keys():
        if k not in seen:
          seen.add(k)
          keys.append(str(k))
    keys = keys[:80]  # prevent absurd widths

    body_rows = result[:max_rows]
    thead = "".join(f"<th>{html.escape(k)}</th>" for k in keys)
    tbody = []
    for row in body_rows:
      tds = "".join(
        f"<td>{html.escape(_safe_str(row.get(k)))}</td>"
        for k in keys
      )
      tbody.append(f"<tr>{tds}</tr>")
    more = ""
    if len(result) > max_rows:
      more = f"<div class='td-small' style='margin-top:8px'>Showing first {max_rows} rows out of {len(result)}.</div>"
    return f"""
      <table class="td-table">
        <thead><tr>{thead}</tr></thead>
        <tbody>{''.join(tbody)}</tbody>
      </table>
      {more}
    """

  # {"columns": [...], "rows":[...]} shape
  if isinstance(result, dict) and isinstance(result.get("rows"), list):
    rows = result.get("rows") or []
    cols = result.get("columns") or []
    if not cols and rows and isinstance(rows[0], dict):
      return _render_table_html(rows, max_rows=max_rows)
    cols = [str(c) for c in (cols or [])][:80]
    thead = "".join(f"<th>{html.escape(c)}</th>" for c in cols) if cols else ""
    body_rows = rows[:max_rows]
    tbody = []
    for r in body_rows:
      if isinstance(r, dict) and cols:
        cells = [r.get(c) for c in cols]
      else:
        cells = list(r) if isinstance(r, (list, tuple)) else [_safe_str(r)]
      if cols and len(cells) < len(cols):
        cells += [""] * (len(cols) - len(cells))
      tds = "".join(f"<td>{html.escape(_safe_str(v))}</td>" for v in cells[: len(cols) or 80])
      tbody.append(f"<tr>{tds}</tr>")
    return f"""
      <table class="td-table">
        <thead><tr>{thead}</tr></thead>
        <tbody>{''.join(tbody)}</tbody>
      </table>
    """

  # list of lists / tuples
  if isinstance(result, list) and result and isinstance(result[0], (list, tuple)):
    rows = result[:max_rows]
    width = min(max(len(r) for r in rows), 80)
    cols = [f"col_{i+1}" for i in range(width)]
    thead = "".join(f"<th>{c}</th>" for c in cols)
    tbody = []
    for r in rows:
      rr = list(r)[:width] + [""] * max(0, width - len(r))
      tds = "".join(f"<td>{html.escape(_safe_str(v))}</td>" for v in rr)
      tbody.append(f"<tr>{tds}</tr>")
    return f"""
      <table class="td-table">
        <thead><tr>{thead}</tr></thead>
        <tbody>{''.join(tbody)}</tbody>
      </table>
    """

  # string fallback
  escaped = html.escape(_safe_str(result))
  return f"<pre style='white-space:pre-wrap;margin:0'>{escaped}</pre>"


def _chatbot_supports_type() -> bool:
  try:
    return "type" in inspect.signature(gr.Chatbot.__init__).parameters
  except Exception:
    return False


def _to_chat_messages(app_messages: Any) -> List[Dict[str, str]]:
  """
  Messages format: [{"role":"user|assistant|system", "content":"..."}]
  Works when gr.Chatbot is in messages mode.
  """
  out: List[Dict[str, str]] = []
  if not isinstance(app_messages, list):
    return out

  for m in app_messages:
    # supports dataclass-like objects with role/content, or dicts
    role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None) or "assistant"
    content = getattr(m, "content", None) if not isinstance(m, dict) else m.get("content")
    role = str(role)
    content = _safe_str(content)

    # normalize any internal roles
    if role == "tool":
      role = "assistant"
      content = f"**DATA**\n{content}"

    if role not in ("user", "assistant", "system"):
      role = "assistant"

    out.append({"role": role, "content": content})
  return out


def _to_chat_tuples(app_messages: Any) -> List[Tuple[str, str]]:
  """
  Tuples format: [(user, assistant), ...]
  Works in older gr.Chatbot (default tuples mode).
  """
  pairs: List[Tuple[str, str]] = []
  if not isinstance(app_messages, list):
    return pairs

  pending_user: str | None = None
  for m in app_messages:
    role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None) or "assistant"
    content = getattr(m, "content", None) if not isinstance(m, dict) else m.get("content")
    role = str(role)
    content = _safe_str(content)

    if role == "user":
      if pending_user is not None:
        pairs.append((pending_user, ""))  # orphan user
      pending_user = content
    else:
      if pending_user is None:
        pending_user = ""  # assistant first
      if role == "tool":
        content = f"**DATA**\n{content}"
      pairs.append((pending_user, content))
      pending_user = None

  if pending_user is not None:
    pairs.append((pending_user, ""))

  return pairs


def build_ui() -> gr.Blocks:
  config = get_config()

  ai_service = None
  ai_init_error = None
  try:
    cred = get_search_credential(config)
    ai_service = AISearchService(config.ai_search_endpoint, cred)
  except Exception as e:
    ai_service = None
    ai_init_error = e

  supports_type = _chatbot_supports_type()

  # Create Blocks with CSS (compatible fallback if css arg not supported)
  blocks_kwargs = {}
  try:
    if "css" in inspect.signature(gr.Blocks.__init__).parameters:
      blocks_kwargs["css"] = CSS
  except Exception:
    pass

  with gr.Blocks(**blocks_kwargs) as demo:
    # ---------- Header ----------
    header_html = f"""
    <div id="td-header">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
        <div id="td-brand">
          <div id="td-logo">TD</div>
          <div id="td-title">
            <h1>NL → SQL Chatbot</h1>
            <div>Azure OpenAI + SQL Server + Azure AI Search metadata</div>
          </div>
        </div>
        <div id="td-pills">
          <div class="td-pill"><span class="td-dot ok"></span>SQL</div>
          <div class="td-pill"><span class="td-dot {'ok' if ai_service else 'bad'}"></span>AI Search</div>
        </div>
      </div>
    </div>
    """
    gr.HTML(header_html)

    # ---------- Hidden init error ----------
    if ai_init_error:
      gr.Markdown(f"**AI Search init error:** `{_safe_str(ai_init_error)}`")

    # ---------- Session state ----------
    state = gr.State({
      "app_messages": [],          # keep internal history (AppChatMessage or dicts)
      "pending_sql": "",
      "last_sql": "",
      "last_result_compact": None,
      "selected_index": None,
    })

    # ---------- Helpers ----------
    def _coerce_state(s: Any) -> Dict[str, Any]:
      s = _as_state(s)
      if "app_messages" not in s or not isinstance(s.get("app_messages"), list):
        s["app_messages"] = []
      if not isinstance(s.get("pending_sql"), str):
        s["pending_sql"] = ""
      if not isinstance(s.get("last_sql"), str):
        s["last_sql"] = ""
      # selected_index can be None/str
      return s

    def _do_turn(user_text: str, s: Any, selected_index: str | None):
      s = _coerce_state(s)

      # Selected index is stored in config for downstream logic
      try:
        setattr(config, "selected_index", selected_index)
      except Exception:
        pass
      s["selected_index"] = selected_index

      user_text = _safe_str(user_text).strip()
      if not user_text:
        chat_value = _to_chat_messages(s["app_messages"]) if supports_type else _to_chat_tuples(s["app_messages"])
        return (
          chat_value,
          s,
          "",
          gr.update(value=s.get("last_sql", "")),
          gr.update(value=_render_table_html(s.get("last_result_compact"))),
        )

      # Defensive: ensure messages is a list (prevents "'str' object has no attribute 'copy'")
      if not isinstance(s.get("app_messages"), list):
        s["app_messages"] = []

      try:
        new_messages, new_pending_sql, last_sql, last_result_compact = handle_user_turn(
          user_text,
          s["app_messages"],
          s["pending_sql"],
          config,
        )
      except Exception as e:
        # Put the error into the chat (as assistant) without breaking format
        err_msg = f"ERROR: {_safe_str(e)}"
        # best-effort append
        msgs = s.get("app_messages") if isinstance(s.get("app_messages"), list) else []
        msgs = list(msgs)
        msgs.append({"role": "assistant", "content": err_msg})
        new_messages, new_pending_sql, last_sql, last_result_compact = msgs, s.get("pending_sql", ""), s.get("last_sql", ""), s.get("last_result_compact")

      s["app_messages"] = new_messages if isinstance(new_messages, list) else []
      s["pending_sql"] = new_pending_sql if isinstance(new_pending_sql, str) else ""
      s["last_sql"] = last_sql if isinstance(last_sql, str) else ""
      s["last_result_compact"] = last_result_compact

      chat_value = _to_chat_messages(s["app_messages"]) if supports_type else _to_chat_tuples(s["app_messages"])

      return (
        chat_value,
        s,
        "",  # clear textbox
        gr.update(value=s["last_sql"]),
        gr.update(value=_render_table_html(s["last_result_compact"])),
      )

    def _clear_all():
      s = {
        "app_messages": [],
        "pending_sql": "",
        "last_sql": "",
        "last_result_compact": None,
        "selected_index": None,
      }
      chat_value = []  # empty
      return (
        chat_value,
        s,
        "",
        gr.update(value=""),
        gr.update(value=_render_table_html(None)),
      )

    def _safe_list_indexes(current_value: str | None):
      if not ai_service:
        return gr.update(), gr.update(value="AI Search not available.", visible=True)
      try:
        indexes = ai_service.list_indexes()
        indexes = indexes or []
        indexes = [str(x) for x in indexes]
        safe_value = current_value if current_value in indexes else (indexes[0] if indexes else None)
        status = f"Refreshed {len(indexes)} index(es)." if indexes else "No indexes found."
        return gr.update(choices=indexes, value=safe_value), gr.update(value=status, visible=True)
      except Exception as e:
        return gr.update(), gr.update(value=f"Failed to refresh indexes: {_safe_str(e)}", visible=True)

    # ---------- Tabs ----------
    with gr.Tabs():
      # =========================
      # Chat Tab
      # =========================
      with gr.Tab("Chat"):
        with gr.Row(equal_height=True):
          # Left: Context + SQL + Results
          with gr.Column(scale=4, min_width=320):
            with gr.Group(elem_classes=["td-card"]):
              gr.Markdown("### Context", elem_classes=["td-section-title"])
              gr.Markdown(
                "Choose the Azure AI Search index used as metadata reference.",
                elem_classes=["td-help"],
              )

              refresh_btn = gr.Button("Refresh Index List", elem_id="refresh-btn")
              index_dropdown = gr.Dropdown(
                label="Metadata Index (used by Chat)",
                choices=[],
                value=None,
              )
              refresh_status = gr.Markdown(visible=False)

              list_tables_btn = gr.Button("List Tables")

            with gr.Group(elem_classes=["td-card"]):
              gr.Markdown("### Generated SQL", elem_classes=["td-section-title"])
              sql_code = gr.Code(value="", language="sql", elem_id="sql-code")

            with gr.Group(elem_classes=["td-card"]):
              gr.Markdown("### Results (Grid)", elem_classes=["td-section-title"])
              results_grid = gr.HTML(value=_render_table_html(None), elem_id="results-grid")

          # Right: Chat
          with gr.Column(scale=8, min_width=520):
            with gr.Group(elem_classes=["td-card"], elem_id="chat-wrap"):
              if supports_type:
                chatbot = gr.Chatbot(type="messages", elem_id="chatbot", show_label=False)
              else:
                chatbot = gr.Chatbot(elem_id="chatbot", show_label=False)

              user_input = gr.Textbox(
                label="",
                placeholder="Ask a question about your data…",
              )

              with gr.Row():
                send_btn = gr.Button("Send", elem_id="send-btn")
                clear_btn = gr.Button("Clear", elem_id="clear-btn")

        # Events (Chat tab)
        refresh_btn.click(
          _safe_list_indexes,
          inputs=[index_dropdown],
          outputs=[index_dropdown, refresh_status],
        )

        # Keep selected index in state, but do NOT trigger refresh automatically
        def _on_index_change(idx: str | None, s: Any):
          s = _coerce_state(s)
          s["selected_index"] = idx
          return gr.update(value=idx), s

        index_dropdown.change(
          _on_index_change,
          inputs=[index_dropdown, state],
          outputs=[index_dropdown, state],
        )

        send_btn.click(
          _do_turn,
          inputs=[user_input, state, index_dropdown],
          outputs=[chatbot, state, user_input, sql_code, results_grid],
        )

        user_input.submit(
          _do_turn,
          inputs=[user_input, state, index_dropdown],
          outputs=[chatbot, state, user_input, sql_code, results_grid],
        )

        list_tables_btn.click(
          lambda s, idx: _do_turn("list tables", s, idx),
          inputs=[state, index_dropdown],
          outputs=[chatbot, state, user_input, sql_code, results_grid],
        )

        clear_btn.click(
          _clear_all,
          inputs=[],
          outputs=[chatbot, state, user_input, sql_code, results_grid],
        )

      # =========================
      # Azure AI Search Tab
      # =========================
      with gr.Tab("Azure AI Search"):
        with gr.Row(equal_height=True):
          with gr.Column(scale=1):
            with gr.Group(elem_classes=["td-card"]):
              gr.Markdown("### Connection", elem_classes=["td-section-title"])
              gr.Markdown(f"**Endpoint:** `{getattr(config, 'ai_search_endpoint', '')}`")
              list_btn = gr.Button("List Indexes")
              idx_dd2 = gr.Dropdown(label="Select Index", choices=[], value=None)
              status_out = gr.Markdown()

          with gr.Column(scale=1):
            with gr.Group(elem_classes=["td-card"]):
              gr.Markdown("### Create Index", elem_classes=["td-section-title"])
              new_index_name = gr.Textbox(label="New Index Name", placeholder="example: edc-metadata")
              create_btn = gr.Button("Create Index")
              create_out = gr.Markdown()

          with gr.Column(scale=1):
            with gr.Group(elem_classes=["td-card"]):
              gr.Markdown("### Upload metadata (pipe-separated)", elem_classes=["td-section-title"])
              file_upload = gr.File(label="Upload Metadata File (.txt/.psv/.csv)")
              upload_btn = gr.Button("Upload to Selected Index")
              upload_out = gr.Markdown()
              stats_out = gr.Markdown()

        def _list_indexes_tab():
          if not ai_service:
            return gr.update(), "AI Search not available."
          try:
            choices = ai_service.list_indexes() or []
            choices = [str(x) for x in choices]
            return gr.update(choices=choices, value=(choices[0] if choices else None)), f"Found {len(choices)} index(es)."
          except Exception as e:
            return gr.update(), f"Failed: {_safe_str(e)}"

        def _create_index(name: str):
          if not ai_service:
            return "AI Search not available."
          name = _safe_str(name).strip()
          if not name:
            return "Please enter an index name."
          try:
            ok, msg = ai_service.create_metadata_index(name)
            return f"{'✅' if ok else '❌'} {msg}"
          except Exception as e:
            return f"❌ Failed: {_safe_str(e)}"

        def _upload(file_obj: Any, selected_idx: str | None):
          if not ai_service:
            return "AI Search not available.", ""
          if not selected_idx:
            return "Please select an index first.", ""
          if not file_obj:
            return "No file selected.", ""
          # gr.File can be path-like or object with .name depending on version
          path = getattr(file_obj, "name", None) or getattr(file_obj, "path", None) or file_obj
          path = _safe_str(path)
          try:
            success, fail, msg = ai_service.ingest_pipe_file(selected_idx, path)
            stats = ai_service.get_index_stats(selected_idx) or {}
            doc_count = stats.get("document_count", stats.get("doc_count", "N/A"))
            return f"✅ {msg} (success={success}, fail={fail})", f"Document count: {doc_count}"
          except Exception as e:
            return f"❌ Failed: {_safe_str(e)}", ""

        list_btn.click(_list_indexes_tab, inputs=[], outputs=[idx_dd2, status_out])
        create_btn.click(_create_index, inputs=[new_index_name], outputs=[create_out])
        upload_btn.click(_upload, inputs=[file_upload, idx_dd2], outputs=[upload_out, stats_out])

  return demo
