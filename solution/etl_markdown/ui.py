# ui.py
from __future__ import annotations

import os
import re
import time
import json
import logging
import threading
import traceback
from typing import Any, Dict, List, Tuple, Optional

import gradio as gr

from app.nl2sql import handle_user_turn
from app.chat_types import AppChatMessage
from app.config import get_config
from app.ai_search_service import AISearchService
from app.identity import get_search_credential, IdentityError


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("ui")


# ----------------------------
# Styling (TD-like, modern)
# ----------------------------
CSS = """
:root{
  --td-green:#1a8f3a;
  --td-green-2:#127031;
  --td-bg:#f6f8f6;
  --td-card:#ffffff;
  --td-border:rgba(0,0,0,.08);
  --td-text:#0b1f12;
  --td-muted:rgba(11,31,18,.65);
}

.gradio-container{
  background: var(--td-bg) !important;
}

#td-header{
  background: var(--td-card);
  border-bottom: 1px solid var(--td-border);
  padding: 14px 16px;
  border-radius: 14px;
  margin-bottom: 12px;
  box-shadow: 0 8px 24px rgba(0,0,0,.05);
}

#td-header .title{
  font-weight: 800;
  font-size: 18px;
  color: var(--td-text);
  margin: 0;
  line-height: 1.2;
}
#td-header .subtitle{
  margin: 6px 0 0 0;
  color: var(--td-muted);
  font-size: 12px;
}

.td-pill{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--td-border);
  background: rgba(26,143,58,.06);
  color: var(--td-text);
  font-size: 12px;
  font-weight: 600;
}

.td-card{
  background: var(--td-card);
  border: 1px solid var(--td-border);
  border-radius: 16px;
  box-shadow: 0 10px 30px rgba(0,0,0,.05);
}

.td-card .gr-form{
  border-radius: 16px;
}

.td-section-title{
  font-weight: 800;
  font-size: 13px;
  color: var(--td-text);
  margin: 0 0 8px 0;
}

.td-muted{
  color: var(--td-muted);
  font-size: 12px;
}

button.primary, .gr-button.primary{
  background: var(--td-green) !important;
  border-color: var(--td-green) !important;
}
button.primary:hover, .gr-button.primary:hover{
  background: var(--td-green-2) !important;
  border-color: var(--td-green-2) !important;
}

.gr-button.secondary{
  border-color: var(--td-border) !important;
}

#status-banner{
  border-radius: 12px;
  padding: 10px 12px;
  border: 1px solid var(--td-border);
  background: rgba(26,143,58,.06);
  color: var(--td-text);
  font-size: 12px;
}

#status-banner.error{
  background: rgba(220,53,69,.08);
  border-color: rgba(220,53,69,.25);
}

#sql-code textarea, #sql-code pre{
  border-radius: 12px !important;
}

#results-card{
  overflow: hidden;
}

#chat-card{
  overflow: hidden;
}

.gr-chatbot{
  border-radius: 14px !important;
}
"""


# ----------------------------
# Helpers
# ----------------------------
def _safe_str(x: Any) -> str:
  try:
    if x is None:
      return ""
    if isinstance(x, (dict, list)):
      return json.dumps(x, ensure_ascii=False, indent=2)
    return str(x)
  except Exception:
    return repr(x)


def to_gradio_messages(app_messages: List[AppChatMessage]) -> List[dict]:
  """
  Gradio Chatbot(type="messages") expects:
    [{"role":"user|assistant|system", "content":"..."}]
  """
  out: List[dict] = []
  for m in app_messages or []:
    role = getattr(m, "role", "assistant") or "assistant"
    content = _safe_str(getattr(m, "content", ""))

    if role == "tool":
      # Show tool output as assistant bubble but clearly labeled.
      content = f"**[DATA]**\n\n{content}"
      role = "assistant"
    elif role == "system":
      # Keep system messages visible (styled like assistant)
      role = "assistant"
      content = f"**[SYSTEM]** {content}"

    out.append({"role": role, "content": content})
  return out


def friendly_message(e: Exception) -> str:
  msg = str(e) if str(e) else e.__class__.__name__
  low = msg.lower()

  if "multiple user assigned identities exist" in low:
    return (
      "Azure Managed Identity authentication failed because **multiple user-assigned identities** are available. "
      "Set one identity explicitly using `AI_SEARCH_MANAGED_IDENTITY_CLIENT_ID` (or `AZURE_CLIENT_ID`) and restart the app."
    )

  if "parameter 'endpoint' must not be none" in low or "endpoint must not be none" in low:
    return (
      "`AI_SEARCH_ENDPOINT` is missing or empty. "
      "Set it to your Azure AI Search endpoint (example: `https://<service>.search.windows.net`) and restart the app."
    )

  if "unauthorized" in low or "forbidden" in low or "403" in low or "401" in low:
    return (
      "Access denied to Azure AI Search. "
      "Make sure your identity has the required role (e.g., **Search Index Data Contributor**) on the Search service."
    )

  if "invalidname" in low or "index name" in low:
    return (
      "Invalid index name. Use only **lowercase letters**, **digits**, and **hyphens (-)**. "
      "It cannot start/end with a hyphen, and must be <= 128 characters."
    )

  if "data incompatible with message format" in low:
    return (
      "Chat message format is invalid for Gradio. Ensure messages are a list of dicts like "
      "`{'role':'user|assistant','content':'...'}`."
    )

  return msg


def sanitize_index_name(name: str) -> Tuple[str, Optional[str]]:
  raw = (name or "").strip()
  n = raw.lower()
  n = re.sub(r"[\s_]+", "-", n)
  n = re.sub(r"[^a-z0-9-]", "-", n)
  n = re.sub(r"-{2,}", "-", n)
  n = n.strip("-")
  n = n[:128].strip("-")

  if not n:
    return "", "Index name is empty after sanitizing. Please enter a valid name (letters/digits/hyphens)."

  note = None
  if n != raw:
    note = f"Index name normalized to: `{n}`"
  return n, note


def _file_path(file_obj: Any) -> Optional[str]:
  if file_obj is None:
    return None
  # gr.File often returns an object with .name or dict-like
  p = getattr(file_obj, "name", None) or getattr(file_obj, "path", None)
  if isinstance(file_obj, dict):
    p = file_obj.get("name") or file_obj.get("path")
  if isinstance(p, str) and p.strip():
    return p
  return None


def _try_pandas_df(x: Any):
  try:
    import pandas as pd  # type: ignore
    if isinstance(x, pd.DataFrame):
      return x
    return None
  except Exception:
    return None


def to_grid_data(last_result_compact: Any) -> Tuple[Any, str]:
  """
  Returns (grid_data_for_gradio, raw_text)
  grid_data can be:
    - pandas DataFrame
    - list[list] (with headers inferred by gr.Dataframe if provided)
    - list[dict]
  """
  raw = _safe_str(last_result_compact)

  # Common shapes
  if last_result_compact is None:
    return [], ""

  # If it's already a DataFrame
  df = _try_pandas_df(last_result_compact)
  if df is not None:
    return df, raw

  # Dict with columns/rows
  if isinstance(last_result_compact, dict):
    cols = last_result_compact.get("columns")
    rows = last_result_compact.get("rows") or last_result_compact.get("data")
    if isinstance(cols, list) and isinstance(rows, list):
      try:
        import pandas as pd  # type: ignore
        return pd.DataFrame(rows, columns=cols), raw
      except Exception:
        return rows, raw
    # If dict-of-lists
    try:
      import pandas as pd  # type: ignore
      return pd.DataFrame(last_result_compact), raw
    except Exception:
      return [last_result_compact], raw

  # List of dict rows
  if isinstance(last_result_compact, list) and last_result_compact and isinstance(last_result_compact[0], dict):
    try:
      import pandas as pd  # type: ignore
      return pd.DataFrame(last_result_compact), raw
    except Exception:
      return last_result_compact, raw

  return [], raw


# ----------------------------
# UI
# ----------------------------
def build_ui() -> gr.Blocks:
  config = get_config()

  # Build AI Search service (optional)
  ai_service: Optional[AISearchService] = None
  ai_init_error: Optional[str] = None
  try:
    credential = get_search_credential(config)
    ai_service = AISearchService(getattr(config, "ai_search_endpoint", None), credential)
  except IdentityError as e:
    ai_init_error = friendly_message(e)
    ai_service = None
  except Exception as e:
    ai_init_error = friendly_message(e)
    ai_service = None

  env_default_index = os.getenv("INDEX_NAME") or os.getenv("AI_SEARCH_INDEX") or getattr(config, "ai_search_index", None)
  default_index = env_default_index if isinstance(env_default_index, str) else None

  # Prevent overlapping refresh/list calls from UI
  refresh_lock = threading.Lock()

  # Theme
  theme = gr.themes.Soft(
    primary_hue="green",
    secondary_hue="emerald",
    neutral_hue="slate",
    font=["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "Arial"],
  )

  with gr.Blocks(theme=theme, css=CSS, title="NL→SQL Chatbot") as demo:
    gr.HTML(
      f"""
      <div id="td-header">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
          <div>
            <p class="title">NL→SQL Chatbot</p>
            <p class="subtitle">Azure OpenAI + SQL Server + Azure AI Search metadata</p>
          </div>
          <div class="td-pill">
            <span style="width:10px;height:10px;border-radius:50%;background:{'#1a8f3a' if ai_service else '#dc3545'};"></span>
            <span>{'AI Search connected' if ai_service else 'AI Search not ready'}</span>
          </div>
        </div>
      </div>
      """
    )

    # Global app state
    state = gr.State(
      {
        "messages": [],
        "pending_sql": "",
        "last_sql": "",
        "last_result_compact": None,
        "selected_index": default_index,
      }
    )

    status_banner = gr.Markdown(
      value=("" if not ai_init_error else f"<div id='status-banner' class='error'>⚠️ {ai_init_error}</div>"),
      visible=bool(ai_init_error),
      elem_id="status-banner",
    )

    # Components that exist in both tabs
    chat_index_dd = gr.Dropdown(
      label="Metadata Index (used by Chat)",
      choices=[],
      value=default_index,
      allow_custom_value=False,
      interactive=True,
    )

    search_index_dd = gr.Dropdown(
      label="Select Index",
      choices=[],
      value=default_index,
      allow_custom_value=False,
      interactive=True,
    )

    # ---------- callbacks ----------
    def _set_banner(text: str, is_error: bool = False):
      if not text:
        return gr.update(visible=False, value="")
      cls = "error" if is_error else ""
      html = f"<div id='status-banner' class='{cls}'> {('⚠️ ' if is_error else '✅ ')}{text}</div>"
      return gr.update(visible=True, value=html)

    def _list_indexes_impl(timeout_s: int = 10) -> Tuple[bool, List[str] | str]:
      if not ai_service:
        return False, "Azure AI Search is not initialized. Check endpoint/identity."
      # Prefer safe_list_indexes if you have it
      fn = getattr(ai_service, "safe_list_indexes", None)
      if callable(fn):
        ok, result = fn(timeout_s=timeout_s)  # type: ignore
        return bool(ok), result
      # Fallback
      try:
        indexes = ai_service.list_indexes()  # type: ignore
        return True, indexes
      except Exception as e:
        return False, e

    def refresh_indexes(current_chat_value: str | None, current_search_value: str | None, st: Dict[str, Any]):
      if not ai_service:
        return (
          gr.update(),
          gr.update(),
          st,
          _set_banner("Azure AI Search is not ready. Check your endpoint and identity.", is_error=True),
        )

      # Re-entrancy guard
      if refresh_lock.locked():
        return (
          gr.update(),
          gr.update(),
          st,
          _set_banner("Refresh already in progress…", is_error=False),
        )

      acquired = refresh_lock.acquire(blocking=False)
      if not acquired:
        return (
          gr.update(),
          gr.update(),
          st,
          _set_banner("Refresh already in progress…", is_error=False),
        )

      try:
        ok, result = _list_indexes_impl(timeout_s=12)
        if not ok:
          msg = friendly_message(result if isinstance(result, Exception) else Exception(_safe_str(result)))
          return (
            gr.update(),
            gr.update(),
            st,
            _set_banner(f"Failed to list indexes. {msg}", is_error=True),
          )

        choices = sorted(list(result)) if isinstance(result, list) else []
        # Preserve selection if still exists
        desired = st.get("selected_index") or current_chat_value or current_search_value
        if desired not in choices:
          desired = choices[0] if choices else None

        st["selected_index"] = desired

        return (
          gr.update(choices=choices, value=desired),
          gr.update(choices=choices, value=desired),
          st,
          _set_banner(f"Indexes refreshed ({len(choices)}).", is_error=False),
        )
      except Exception as e:
        msg = friendly_message(e)
        return (
          gr.update(),
          gr.update(),
          st,
          _set_banner(f"Refresh failed. {msg}", is_error=True),
        )
      finally:
        try:
          refresh_lock.release()
        except Exception:
          pass

    def sync_from_chat(new_idx: str | None, st: Dict[str, Any]):
      st["selected_index"] = new_idx
      return gr.update(value=new_idx), st

    def sync_from_search(new_idx: str | None, st: Dict[str, Any]):
      st["selected_index"] = new_idx
      return gr.update(value=new_idx), st

    def send_user_text(user_text: str, st: Dict[str, Any], selected_index: str | None):
      messages: List[AppChatMessage] = st.get("messages") or []
      pending_sql: str = st.get("pending_sql") or ""

      # make selected index available for the engine
      try:
        setattr(config, "selected_index", selected_index)
      except Exception:
        pass

      try:
        new_messages, new_pending_sql, last_sql, last_result_compact = handle_user_turn(
          user_text, messages, pending_sql, config
        )

        st["messages"] = new_messages
        st["pending_sql"] = new_pending_sql
        st["last_sql"] = last_sql
        st["last_result_compact"] = last_result_compact
        st["selected_index"] = selected_index

        chat_payload = to_gradio_messages(new_messages)
        grid, raw = to_grid_data(last_result_compact)

        return (
          chat_payload,
          st,
          "",
          last_sql or "",
          grid,
          raw,
          _set_banner("", is_error=False),
        )
      except Exception as e:
        # Always return valid outputs (prevents ERR_INCOMPLETE_CHUNKED_ENCODING)
        msg = friendly_message(e)
        tb = traceback.format_exc()
        logger.error("Chat error: %s\n%s", e, tb)

        # Add a friendly assistant message so user sees something useful
        try:
          messages = st.get("messages") or []
          messages = list(messages)
          messages.append(AppChatMessage(role="assistant", content=f"⚠️ {msg}"))
          st["messages"] = messages
        except Exception:
          pass

        return (
          to_gradio_messages(st.get("messages") or []),
          st,
          "",
          st.get("last_sql") or "",
          [],
          "",
          _set_banner(msg, is_error=True),
        )

    def list_tables(st: Dict[str, Any], selected_index: str | None):
      return send_user_text("list tables", st, selected_index)

    def create_index(new_name: str, st: Dict[str, Any]):
      if not ai_service:
        return (
          gr.update(),
          gr.update(),
          st,
          _set_banner("Azure AI Search is not ready. Check your endpoint and identity.", is_error=True),
        )

      clean, note = sanitize_index_name(new_name)
      if not clean:
        return (
          gr.update(),
          gr.update(),
          st,
          _set_banner(note or "Invalid index name.", is_error=True),
        )

      try:
        fn = getattr(ai_service, "create_metadata_index", None)
        if not callable(fn):
          return (
            gr.update(),
            gr.update(),
            st,
            _set_banner("AISearchService.create_metadata_index() is missing.", is_error=True),
          )

        ok, msg = fn(clean)  # type: ignore
        if not ok:
          return (
            gr.update(),
            gr.update(),
            st,
            _set_banner(f"Failed to create index. {friendly_message(Exception(_safe_str(msg)))}", is_error=True),
          )

        # Refresh list after create
        ok2, result2 = _list_indexes_impl(timeout_s=12)
        if ok2 and isinstance(result2, list):
          choices = sorted(result2)
          st["selected_index"] = clean
          banner = f"Index created: `{clean}`."
          if note:
            banner += f" {note}"
          return (
            gr.update(choices=choices, value=clean),
            gr.update(choices=choices, value=clean),
            st,
            _set_banner(banner, is_error=False),
          )

        banner = f"Index created: `{clean}`."
        if note:
          banner += f" {note}"
        st["selected_index"] = clean
        return (
          gr.update(value=clean),
          gr.update(value=clean),
          st,
          _set_banner(banner, is_error=False),
        )

      except Exception as e:
        return (
          gr.update(),
          gr.update(),
          st,
          _set_banner(f"Create index failed. {friendly_message(e)}", is_error=True),
        )

    def upload_metadata(file_obj: Any, selected_idx: str | None, st: Dict[str, Any]):
      if not ai_service:
        return _set_banner("Azure AI Search is not ready. Check your endpoint and identity.", is_error=True), st

      if not selected_idx:
        return _set_banner("Please select an index first.", is_error=True), st

      path = _file_path(file_obj)
      if not path:
        return _set_banner("No file selected.", is_error=True), st

      try:
        ingest = getattr(ai_service, "ingest_pipe_file", None)
        if not callable(ingest):
          return _set_banner("AISearchService.ingest_pipe_file() is missing.", is_error=True), st

        ok, failed, msg = ingest(selected_idx, path)  # type: ignore
        if not ok:
          return _set_banner(f"Upload failed. {friendly_message(Exception(_safe_str(msg)))}", is_error=True), st

        # Optional stats
        stats_fn = getattr(ai_service, "get_index_stats", None)
        stats_note = ""
        if callable(stats_fn):
          try:
            stats = stats_fn(selected_idx)  # type: ignore
            if isinstance(stats, dict):
              dc = stats.get("document_count") or stats.get("documentCount") or stats.get("count")
              if dc is not None:
                stats_note = f" Document count: **{dc}**."
          except Exception:
            pass

        return _set_banner(f"Upload complete. Failed docs: **{failed}**.{stats_note}", is_error=False), st

      except Exception as e:
        return _set_banner(f"Upload failed. {friendly_message(e)}", is_error=True), st

    # ----------------------------
    # Layout
    # ----------------------------
    with gr.Tabs():
      # ========== CHAT TAB ==========
      with gr.Tab("Chat"):
        with gr.Row(equal_height=True):
          # Sidebar
          with gr.Column(scale=4, min_width=320):
            with gr.Group(elem_classes=["td-card"]):
              gr.Markdown("<div class='td-section-title'>Context</div>")
              gr.Markdown("<div class='td-muted'>Choose which Azure AI Search index provides metadata context.</div>")
              chat_refresh_btn = gr.Button("Refresh Index List", variant="secondary")
              gr.Markdown("", elem_id="spacer-1")

              # Index dropdown (shared)
              chat_index_dd.render()

              gr.Markdown("<div style='height:10px;'></div>")
              quick_tables = gr.Button("List Tables", variant="secondary")
              gr.Markdown(
                "<div class='td-muted'>Tip: Use <b>List Tables</b> to quickly verify metadata/search connectivity.</div>"
              )

            gr.Markdown("<div style='height:10px;'></div>")
            with gr.Group(elem_classes=["td-card"]):
              gr.Markdown("<div class='td-section-title'>Generated SQL</div>")
              sql_code = gr.Code(value="", language="sql", elem_id="sql-code")
              gr.Markdown("<div class='td-muted'>This is what will run against SQL Server.</div>")

          # Main chat + results
          with gr.Column(scale=8, min_width=520):
            with gr.Group(elem_classes=["td-card"], elem_id="chat-card"):
              chatbot = gr.Chatbot(
                label="Chat",
                type="messages",
                height=420,
                show_copy_button=True,
              )
              user_input = gr.Textbox(
                placeholder="Ask a question about your data…",
                label="",
                lines=2,
              )
              with gr.Row():
                send_btn = gr.Button("Send", variant="primary")
                clear_btn = gr.Button("Clear", variant="secondary")

            gr.Markdown("<div style='height:10px;'></div>")
            with gr.Group(elem_classes=["td-card"], elem_id="results-card"):
              gr.Markdown("<div class='td-section-title'>Results</div>")
              results_df = gr.Dataframe(
                value=[],
                label="Grid view",
                interactive=False,
                height=260,
              )
              results_raw = gr.Code(value="", language="json", label="Raw output (debug)")

        # Chat events
        send_btn.click(
          send_user_text,
          inputs=[user_input, state, chat_index_dd],
          outputs=[chatbot, state, user_input, sql_code, results_df, results_raw, status_banner],
        )
        user_input.submit(
          send_user_text,
          inputs=[user_input, state, chat_index_dd],
          outputs=[chatbot, state, user_input, sql_code, results_df, results_raw, status_banner],
        )

        quick_tables.click(
          list_tables,
          inputs=[state, chat_index_dd],
          outputs=[chatbot, state, user_input, sql_code, results_df, results_raw, status_banner],
        )

        def _clear():
          return [], {"messages": [], "pending_sql": "", "last_sql": "", "last_result_compact": None, "selected_index": None}, "", "", [], "", _set_banner("", False)

        clear_btn.click(
          _clear,
          inputs=[],
          outputs=[chatbot, state, user_input, sql_code, results_df, results_raw, status_banner],
        )

        chat_refresh_btn.click(
          refresh_indexes,
          inputs=[chat_index_dd, search_index_dd, state],
          outputs=[chat_index_dd, search_index_dd, state, status_banner],
        )

      # ========== AZURE AI SEARCH TAB ==========
      with gr.Tab("Azure AI Search"):
        with gr.Row(equal_height=True):
          with gr.Column(scale=6, min_width=420):
            with gr.Group(elem_classes=["td-card"]):
              endpoint = getattr(config, "ai_search_endpoint", None) or os.getenv("AI_SEARCH_ENDPOINT", "")
              gr.Markdown("<div class='td-section-title'>Connection</div>")
              gr.Markdown(f"<div class='td-muted'><b>Endpoint:</b> {endpoint}</div>")

              with gr.Row():
                list_btn = gr.Button("List Indexes", variant="secondary")
                refresh_btn2 = gr.Button("Refresh", variant="secondary")

              search_index_dd.render()

              new_index_name = gr.Textbox(label="New Index Name", placeholder="example: edc-metadata")
              create_btn = gr.Button("Create Index", variant="primary")

            gr.Markdown("<div style='height:10px;'></div>")
            with gr.Group(elem_classes=["td-card"]):
              gr.Markdown("<div class='td-section-title'>Upload metadata (pipe-separated)</div>")
              upload_file = gr.File(
                label="Upload Metadata File (.txt / .psv / .csv)",
                file_types=[".txt", ".psv", ".csv"],
              )
              upload_btn = gr.Button("Upload to Selected Index", variant="primary")

          with gr.Column(scale=6, min_width=420):
            with gr.Group(elem_classes=["td-card"]):
              gr.Markdown("<div class='td-section-title'>Status</div>")
              gr.Markdown("<div class='td-muted'>Any operation issues will show here.</div>")
              gr.Markdown("", elem_id="azure-status-spacer")
              # Reuse banner
              status_banner.render()

        # Sync selection between dropdowns
        chat_index_dd.change(sync_from_chat, inputs=[chat_index_dd, state], outputs=[search_index_dd, state])
        search_index_dd.change(sync_from_search, inputs=[search_index_dd, state], outputs=[chat_index_dd, state])

        # Index management events
        list_btn.click(
          refresh_indexes,
          inputs=[chat_index_dd, search_index_dd, state],
          outputs=[chat_index_dd, search_index_dd, state, status_banner],
        )
        refresh_btn2.click(
          refresh_indexes,
          inputs=[chat_index_dd, search_index_dd, state],
          outputs=[chat_index_dd, search_index_dd, state, status_banner],
        )

        create_btn.click(
          create_index,
          inputs=[new_index_name, state],
          outputs=[chat_index_dd, search_index_dd, state, status_banner],
        )

        upload_btn.click(
          upload_metadata,
          inputs=[upload_file, search_index_dd, state],
          outputs=[status_banner, state],
        )

    # Initial load: populate indexes once (if possible)
    def _init_load(st: Dict[str, Any]):
      if not ai_service:
        return gr.update(), gr.update(), st, _set_banner(ai_init_error or "Azure AI Search not ready.", is_error=True)

      ok, result = _list_indexes_impl(timeout_s=12)
      if not ok or not isinstance(result, list):
        msg = friendly_message(result if isinstance(result, Exception) else Exception(_safe_str(result)))
        return gr.update(), gr.update(), st, _set_banner(f"Failed to list indexes. {msg}", is_error=True)

      choices = sorted(result)
      desired = st.get("selected_index") or default_index
      if desired not in choices:
        desired = choices[0] if choices else None
      st["selected_index"] = desired

      return (
        gr.update(choices=choices, value=desired),
        gr.update(choices=choices, value=desired),
        st,
        _set_banner("", is_error=False),
      )

    demo.load(
      _init_load,
      inputs=[state],
      outputs=[chat_index_dd, search_index_dd, state, status_banner],
    )

  return demo


if __name__ == "__main__":
  demo = build_ui()
  demo.queue(default_concurrency_limit=int(os.getenv("GRADIO_CONCURRENCY", "20")))
  demo.launch(
    server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
    server_port=int(os.getenv("PORT", "7860")),
    show_error=True,
  )
