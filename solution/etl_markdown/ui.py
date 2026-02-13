# ui.py (compat-safe across Gradio versions: filters unsupported kwargs like Dataframe(height=...) )
from __future__ import annotations

import os
import re
import json
import time
import logging
import threading
import traceback
import inspect
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

from app.nl2sql import handle_user_turn
from app.chat_types import AppChatMessage
from app.config import get_config
from app.ai_search_service import AISearchService
from app.identity import get_search_credential, IdentityError

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("ui")

# ---------- Styling (TD-ish green/white, modern cards) ----------
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
.gradio-container{ background: var(--td-bg) !important; }

#td-header{
  background: var(--td-card);
  border: 1px solid var(--td-border);
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
  padding: 12px;
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
.gr-chatbot{
  border-radius: 14px !important;
}
"""

# ---------- Compatibility helpers (drop unsupported kwargs) ----------
def _filter_kwargs(callable_obj, kwargs: Dict[str, Any]) -> Dict[str, Any]:
  try:
    # class -> use __init__, function -> use itself
    target = callable_obj.__init__ if inspect.isclass(callable_obj) else callable_obj
    sig = inspect.signature(target)
    allowed = set(sig.parameters.keys())
    allowed.discard("self")
    return {k: v for k, v in kwargs.items() if k in allowed}
  except Exception:
    # if we can't inspect, just pass as-is
    return kwargs

def safe_make(component_cls, **kwargs):
  return component_cls(**_filter_kwargs(component_cls, kwargs))

def safe_update(**kwargs):
  # gr.update exists on most versions; if not, return dict (rare)
  try:
    return gr.update(**kwargs)
  except Exception:
    return kwargs

# ---------- Utilities ----------
def _safe_str(x: Any) -> str:
  try:
    if x is None:
      return ""
    if isinstance(x, (dict, list)):
      return json.dumps(x, ensure_ascii=False, indent=2)
    return str(x)
  except Exception:
    return repr(x)

def friendly_message(e: Exception) -> str:
  msg = str(e) if str(e) else e.__class__.__name__
  low = msg.lower()
  if "multiple user assigned identities exist" in low:
    return (
      "Azure Managed Identity error: multiple user-assigned identities exist. "
      "Set `AI_SEARCH_MANAGED_IDENTITY_CLIENT_ID` (or `AZURE_CLIENT_ID`) and restart."
    )
  if "parameter 'endpoint' must not be none" in low or "endpoint must not be none" in low:
    return "Missing `AI_SEARCH_ENDPOINT`. Set it (e.g. `https://<service>.search.windows.net`) and restart."
  if "unauthorized" in low or "forbidden" in low or "401" in low or "403" in low:
    return "Access denied to Azure AI Search. Ensure the identity has `Search Index Data Contributor` on the Search service."
  if "invalidname" in low or "index name" in low:
    return "Invalid index name. Use lowercase letters, digits, hyphens; cannot start/end with hyphen; <=128 chars."
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
    return "", "Index name is empty after sanitizing."
  note = None
  if n != raw:
    note = f"Normalized to `{n}`"
  return n, note

def _file_path(file_obj: Any) -> Optional[str]:
  if file_obj is None:
    return None
  if isinstance(file_obj, dict):
    p = file_obj.get("name") or file_obj.get("path")
    return p if isinstance(p, str) and p.strip() else None
  p = getattr(file_obj, "name", None) or getattr(file_obj, "path", None)
  return p if isinstance(p, str) and p.strip() else None

# ---- tuple-based chatbot payload (works on older Gradio; no Chatbot(type="messages")) ----
def to_chat_pairs(app_messages: List[AppChatMessage]) -> List[Tuple[str, str]]:
  pairs: List[Tuple[str, str]] = []
  pending_user: Optional[str] = None

  def append_assistant(txt: str):
    if not pairs:
      pairs.append(("", txt))
    else:
      u, a = pairs[-1]
      pairs[-1] = (u, (a + "\n\n" + txt).strip())

  for m in app_messages or []:
    role = getattr(m, "role", "assistant") or "assistant"
    content = _safe_str(getattr(m, "content", ""))

    if role == "user":
      pending_user = content
      continue

    if role == "tool":
      content = f"[DATA]\n{content}"
    elif role == "system":
      content = f"[SYSTEM] {content}"

    if pending_user is None:
      append_assistant(content)
    else:
      pairs.append((pending_user, content))
      pending_user = None

  if pending_user is not None:
    pairs.append((pending_user, ""))

  return pairs

def to_grid_data(last_result_compact: Any) -> Tuple[Any, str]:
  raw = _safe_str(last_result_compact)
  if last_result_compact is None:
    return [], ""

  try:
    import pandas as pd  # type: ignore
    if isinstance(last_result_compact, pd.DataFrame):
      return last_result_compact, raw
  except Exception:
    pass

  if isinstance(last_result_compact, dict):
    cols = last_result_compact.get("columns")
    rows = last_result_compact.get("rows") or last_result_compact.get("data")
    if isinstance(cols, list) and isinstance(rows, list):
      try:
        import pandas as pd  # type: ignore
        return pd.DataFrame(rows, columns=cols), raw
      except Exception:
        return rows, raw
    try:
      import pandas as pd  # type: ignore
      return pd.DataFrame(last_result_compact), raw
    except Exception:
      return [last_result_compact], raw

  if isinstance(last_result_compact, list) and last_result_compact and isinstance(last_result_compact[0], dict):
    try:
      import pandas as pd  # type: ignore
      return pd.DataFrame(last_result_compact), raw
    except Exception:
      return last_result_compact, raw

  return [], raw

# ---------- Main UI ----------
def build_ui() -> gr.Blocks:
  config = get_config()

  ai_service: Optional[AISearchService] = None
  ai_init_error: Optional[str] = None

  try:
    credential = get_search_credential(config)
    ai_service = AISearchService(getattr(config, "ai_search_endpoint", None), credential)
  except IdentityError as e:
    ai_init_error = friendly_message(e)
  except Exception as e:
    ai_init_error = friendly_message(e)

  env_default_index = os.getenv("INDEX_NAME") or os.getenv("AI_SEARCH_INDEX") or getattr(config, "ai_search_index", None)
  default_index = env_default_index if isinstance(env_default_index, str) and env_default_index.strip() else None

  refresh_lock = threading.Lock()

  def _banner(text: str, is_error: bool = False):
    if not text:
      return safe_update(visible=False, value="")
    cls = "error" if is_error else ""
    prefix = "⚠️ " if is_error else "✅ "
    return safe_update(visible=True, value=f"<div id='status-banner' class='{cls}'>{prefix}{text}</div>")

  def _list_indexes(timeout_s: int = 12) -> Tuple[bool, List[str] | Exception]:
    if not ai_service:
      return False, Exception("Azure AI Search is not initialized.")
    fn = getattr(ai_service, "safe_list_indexes", None)
    if callable(fn):
      ok, result = fn(timeout_s=timeout_s)  # type: ignore
      if ok and isinstance(result, list):
        return True, result
      return False, Exception(_safe_str(result))
    try:
      result = ai_service.list_indexes()  # type: ignore
      if isinstance(result, list):
        return True, result
      return False, Exception("Unexpected list_indexes() response.")
    except Exception as e:
      return False, e

  state = gr.State(
    {
      "messages": [],
      "pending_sql": "",
      "last_sql": "",
      "last_result_compact": None,
      "selected_index": default_index,
      "sync_count": 0,
    }
  )

  # Use Blocks(css=...) only if supported; otherwise we pass css to launch.
  blocks_kwargs = {"title": "NL→SQL Chatbot"}
  try:
    if "css" in inspect.signature(gr.Blocks).parameters:
      blocks_kwargs["css"] = CSS
  except Exception:
    pass

  with gr.Blocks(**blocks_kwargs) as demo:
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

    status_banner = safe_make(
      gr.Markdown,
      value=("" if not ai_init_error else f"<div id='status-banner' class='error'>⚠️ {ai_init_error}</div>"),
      visible=bool(ai_init_error),
    )

    # declare components once (no render(), no duplicates)
    chat_index_dd = safe_make(gr.Dropdown, label="Metadata Index (used by Chat)", choices=[], value=None, interactive=True)
    search_index_dd = safe_make(gr.Dropdown, label="Select Index", choices=[], value=None, interactive=True)

    def refresh_indexes(st: Dict[str, Any], chat_val: Optional[str], search_val: Optional[str]):
      if not ai_service:
        return safe_update(), safe_update(), st, _banner(ai_init_error or "Azure AI Search not ready.", True)

      if refresh_lock.locked():
        return safe_update(), safe_update(), st, _banner("Refresh already in progress…", False)

      if not refresh_lock.acquire(blocking=False):
        return safe_update(), safe_update(), st, _banner("Refresh already in progress…", False)

      try:
        ok, result = _list_indexes(timeout_s=12)
        if not ok:
          msg = friendly_message(result if isinstance(result, Exception) else Exception(_safe_str(result)))
          return safe_update(), safe_update(), st, _banner(f"Failed to list indexes. {msg}", True)

        choices = sorted(result)  # type: ignore[arg-type]
        desired = st.get("selected_index") or chat_val or search_val or default_index
        if desired not in choices:
          desired = choices[0] if choices else None

        st["selected_index"] = desired
        st["sync_count"] = 2

        return (
          safe_update(choices=choices, value=desired),
          safe_update(choices=choices, value=desired),
          st,
          _banner(f"Indexes refreshed ({len(choices)}).", False),
        )
      finally:
        try:
          refresh_lock.release()
        except Exception:
          pass

    def on_chat_index_change(new_idx: Optional[str], st: Dict[str, Any]):
      if (st.get("sync_count") or 0) > 0:
        st["sync_count"] = max(0, int(st.get("sync_count", 0)) - 1)
        st["selected_index"] = new_idx
        return safe_update(), st
      st["selected_index"] = new_idx
      st["sync_count"] = 1
      return safe_update(value=new_idx), st

    def on_search_index_change(new_idx: Optional[str], st: Dict[str, Any]):
      if (st.get("sync_count") or 0) > 0:
        st["sync_count"] = max(0, int(st.get("sync_count", 0)) - 1)
        st["selected_index"] = new_idx
        return safe_update(), st
      st["selected_index"] = new_idx
      st["sync_count"] = 1
      return safe_update(value=new_idx), st

    def send_user_text(user_text: str, st: Dict[str, Any], selected_index: Optional[str]):
      messages: List[AppChatMessage] = st.get("messages") or []
      pending_sql: str = st.get("pending_sql") or ""
      selected_index = selected_index or st.get("selected_index")

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

        chat_pairs = to_chat_pairs(new_messages)
        grid, raw = to_grid_data(last_result_compact)

        return (
          chat_pairs,
          st,
          "",
          last_sql or "",
          grid,
          raw,
          _banner("", False),
        )
      except Exception as e:
        logger.error("Chat error: %s\n%s", e, traceback.format_exc())
        return (
          to_chat_pairs(st.get("messages") or []),
          st,
          "",
          st.get("last_sql") or "",
          [],
          "",
          _banner(friendly_message(e), True),
        )

    def list_tables(st: Dict[str, Any], selected_index: Optional[str]):
      return send_user_text("list tables", st, selected_index)

    def create_index(new_name: str, st: Dict[str, Any]):
      if not ai_service:
        return safe_update(), safe_update(), st, _banner(ai_init_error or "Azure AI Search not ready.", True)

      clean, note = sanitize_index_name(new_name)
      if not clean:
        return safe_update(), safe_update(), st, _banner(note or "Invalid index name.", True)

      try:
        fn = getattr(ai_service, "create_metadata_index", None)
        if not callable(fn):
          return safe_update(), safe_update(), st, _banner("AISearchService.create_metadata_index() is missing.", True)

        ok, msg = fn(clean)  # type: ignore
        if not ok:
          return safe_update(), safe_update(), st, _banner(f"Create index failed. {friendly_message(Exception(_safe_str(msg)))}", True)

        ok2, result2 = _list_indexes(timeout_s=12)
        choices = sorted(result2) if ok2 else []  # type: ignore[arg-type]

        st["selected_index"] = clean
        st["sync_count"] = 2

        banner = f"Index created: `{clean}`."
        if note:
          banner += f" {note}"

        return (
          safe_update(choices=choices, value=clean),
          safe_update(choices=choices, value=clean),
          st,
          _banner(banner, False),
        )

      except Exception as e:
        return safe_update(), safe_update(), st, _banner(f"Create index failed. {friendly_message(e)}", True)

    def upload_metadata(file_obj: Any, selected_idx: Optional[str], st: Dict[str, Any]):
      if not ai_service:
        return _banner(ai_init_error or "Azure AI Search not ready.", True), st

      selected_idx = selected_idx or st.get("selected_index")
      if not selected_idx:
        return _banner("Please select an index first.", True), st

      path = _file_path(file_obj)
      if not path:
        return _banner("No file selected.", True), st

      try:
        ingest = getattr(ai_service, "ingest_pipe_file", None)
        if not callable(ingest):
          return _banner("AISearchService.ingest_pipe_file() is missing.", True), st

        ok, failed, msg = ingest(selected_idx, path)  # type: ignore
        if not ok:
          return _banner(f"Upload failed. {friendly_message(Exception(_safe_str(msg)))}", True), st

        stats_note = ""
        stats_fn = getattr(ai_service, "get_index_stats", None)
        if callable(stats_fn):
          try:
            stats = stats_fn(selected_idx)  # type: ignore
            if isinstance(stats, dict):
              dc = stats.get("document_count") or stats.get("documentCount") or stats.get("count")
              if dc is not None:
                stats_note = f" Document count: **{dc}**."
          except Exception:
            pass

        return _banner(f"Upload complete. Failed docs: **{failed}**.{stats_note}", False), st

      except Exception as e:
        return _banner(f"Upload failed. {friendly_message(e)}", True), st

    # ---------------- Layout ----------------
    with gr.Tabs():
      with gr.Tab("Chat"):
        with gr.Row():
          with gr.Column(scale=4):
            gr.HTML("<div class='td-card'><div class='td-section-title'>Context</div><div class='td-muted'>Choose the Azure AI Search index used as reference.</div></div>")
            chat_refresh_btn = safe_make(gr.Button, value="Refresh Index List")
            chat_index_dd.render()  # ensures it belongs to this tab
            list_tables_btn = safe_make(gr.Button, value="List Tables")
            gr.HTML("<div style='height:10px'></div>")
            gr.HTML("<div class='td-card'><div class='td-section-title'>Generated SQL</div></div>")
            sql_code = safe_make(gr.Code, value="", language="sql")

          with gr.Column(scale=8):
            gr.HTML("<div class='td-card'><div class='td-section-title'>Chat</div></div>")
            chatbot = safe_make(gr.Chatbot, label="Chat")  # NO type=..., NO height=...
            user_input = safe_make(gr.Textbox, placeholder="Ask a question about your data…", lines=2, label="")
            with gr.Row():
              send_btn = safe_make(gr.Button, value="Send")
              clear_btn = safe_make(gr.Button, value="Clear")
            gr.HTML("<div style='height:10px'></div>")
            gr.HTML("<div class='td-card'><div class='td-section-title'>Results (Grid)</div><div class='td-muted'>Shown when SQL returns tabular results.</div></div>")
            # ✅ NO height=... (your error). Also filtered by safe_make anyway.
            results_df = safe_make(gr.Dataframe, value=[], interactive=False, label="Grid view")
            results_raw = safe_make(gr.Code, value="", language="json", label="Raw output (debug)")

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
        list_tables_btn.click(
          list_tables,
          inputs=[state, chat_index_dd],
          outputs=[chatbot, state, user_input, sql_code, results_df, results_raw, status_banner],
        )

        def _clear():
          st = {
            "messages": [],
            "pending_sql": "",
            "last_sql": "",
            "last_result_compact": None,
            "selected_index": None,
            "sync_count": 0,
          }
          return [], st, "", "", [], "", _banner("", False)

        clear_btn.click(
          _clear,
          inputs=[],
          outputs=[chatbot, state, user_input, sql_code, results_df, results_raw, status_banner],
        )

      with gr.Tab("Azure AI Search"):
        endpoint = getattr(config, "ai_search_endpoint", None) or os.getenv("AI_SEARCH_ENDPOINT", "")
        gr.HTML(f"<div class='td-card'><div class='td-section-title'>Connection</div><div class='td-muted'><b>Endpoint:</b> {endpoint}</div></div>")
        with gr.Row():
          list_btn = safe_make(gr.Button, value="List Indexes")
          refresh_btn = safe_make(gr.Button, value="Refresh")
        search_index_dd.render()
        new_index_name = safe_make(gr.Textbox, label="New Index Name", placeholder="example: edc-metadata")
        create_btn = safe_make(gr.Button, value="Create Index")
        gr.HTML("<div style='height:10px'></div>")
        gr.HTML("<div class='td-card'><div class='td-section-title'>Upload metadata (pipe-separated)</div></div>")
        upload_file = safe_make(gr.File, label="Upload Metadata File (.txt / .psv / .csv)")
        upload_btn = safe_make(gr.Button, value="Upload to Selected Index")

    # ---------- wiring ----------
    chat_refresh_btn.click(
      refresh_indexes,
      inputs=[state, chat_index_dd, search_index_dd],
      outputs=[chat_index_dd, search_index_dd, state, status_banner],
    )
    list_btn.click(
      refresh_indexes,
      inputs=[state, chat_index_dd, search_index_dd],
      outputs=[chat_index_dd, search_index_dd, state, status_banner],
    )
    refresh_btn.click(
      refresh_indexes,
      inputs=[state, chat_index_dd, search_index_dd],
      outputs=[chat_index_dd, search_index_dd, state, status_banner],
    )

    chat_index_dd.change(on_chat_index_change, inputs=[chat_index_dd, state], outputs=[search_index_dd, state])
    search_index_dd.change(on_search_index_change, inputs=[search_index_dd, state], outputs=[chat_index_dd, state])

    create_btn.click(create_index, inputs=[new_index_name, state], outputs=[chat_index_dd, search_index_dd, state, status_banner])
    upload_btn.click(upload_metadata, inputs=[upload_file, search_index_dd, state], outputs=[status_banner, state])

    # Initial load: populate indexes
    def _init(st: Dict[str, Any]):
      if not ai_service:
        return safe_update(), safe_update(), st, _banner(ai_init_error or "Azure AI Search not ready.", True)
      ok, result = _list_indexes(timeout_s=12)
      if not ok:
        return safe_update(), safe_update(), st, _banner(f"Failed to list indexes. {friendly_message(result)}", True)

      choices = sorted(result)  # type: ignore[arg-type]
      desired = st.get("selected_index") or default_index
      if desired not in choices:
        desired = choices[0] if choices else None

      st["selected_index"] = desired
      st["sync_count"] = 2

      return (
        safe_update(choices=choices, value=desired),
        safe_update(choices=choices, value=desired),
        st,
        _banner("", False),
      )

    demo.load(_init, inputs=[state], outputs=[chat_index_dd, search_index_dd, state, status_banner])

  return demo


if __name__ == "__main__":
  demo = build_ui()

  # Queue if available
  if hasattr(demo, "queue"):
    try:
      demo.queue(default_concurrency_limit=int(os.getenv("GRADIO_CONCURRENCY", "20")))
    except Exception:
      pass

  # Launch with css if supported at launch()
  launch_kwargs = dict(
    server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
    server_port=int(os.getenv("PORT", "7860")),
    show_error=True,
    share=False,
  )
  try:
    if "css" in inspect.signature(demo.launch).parameters:
      launch_kwargs["css"] = CSS
  except Exception:
    pass

  demo.launch(**launch_kwargs)

