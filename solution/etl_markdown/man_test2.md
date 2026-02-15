# TD‑Themed Text‑to‑SQL UI (Streamlit) — Copilot Build Spec (No implementation code)

> **Purpose:** This doc is meant to be pasted into **GitHub Copilot Chat** inside the repo so it can implement the UI step‑by‑step.


## 1) Pick the UI framework (decision)

Use **Streamlit** for maximum flexibility and fastest TD‑themed UI iteration.

---

## 2) Target UX (what the user sees)

### Layout
- **Header bar** (TD green accents)
  - TD logo (left)
  - App name (e.g., “Text2SQL (POC)”) (center)
  - Debug toggle (right) visible only when `DEBUG=true`
- **Main area**
  - **Chat transcript** (assistant + user bubbles)
  - **Chat input** at bottom (Enter submits)
- **Right sidebar (collapsible)**
  - **Data source controls**
    - “Execution target”: SQLite (now), Oracle (later, placeholder)
    - “Max rows” default 50, adjustable
  - **Indexes**
    - show the index names (meta_data_field/meta_data_table/meta_data_relationship)
    - show “Refresh metadata” button (calls existing indexing flow later)
  - **Session controls**
    - Clear chat
    - Download conversation/logs (JSONL)
- **Below assistant message (per answer)**
  - Card 1: **SQL** (expandable)
  - Card 2: **Results grid** (st.dataframe)
  - Card 3: **Explanation** (short, business‑friendly)
  - Card 4 (debug only): **Trace / Logs stream** (live during run)

### Streaming logs (must)
While the assistant is working, show a live “Trace” stream with events like:
- `Intent detected: ...`
- `Need metadata? yes -> searching meta_data_*`
- `Building prompt`
- `Generated SQL`
- `Sanitizing SQL`
- `Validating SQL syntax`
- `Executing SQL`
- `Rows returned: N`
- `0 rows fallback triggered`
- `Clarifying question needed: ...`

### Clarification behavior
If the orchestrator is not confident / missing info:
- Assistant asks a **single clear question** (not multiple).
- Provide **choices** when possible (chips or numbered options).
- Do **not** hallucinate table/columns if not found in metadata.

### Keyboard shortcuts
- **Enter** submits (Streamlit `st.chat_input` default behavior).
- Optional: **Ctrl+Enter** submit if you choose a multi-line input (only if you implement a safe component; otherwise skip).

---

## 3) Minimal dependencies (keep it TD‑friendly)

Add to `requirements.txt` (only if missing):
- `streamlit`
- (already used) `python-dotenv`
- (already used) `azure-identity`
- (already used) `azure-search-documents`
- (already used) `pandas` (for displaying results)

**Do NOT** add heavy “agentic” libs unless explicitly approved.

---

## 4) File/Folder structure (create these)

Create this UI package layout:

```
app/
  ui/
    __init__.py
    streamlit_app.py          # entry point: `streamlit run app/ui/streamlit_app.py`
    theme.py                  # TD theme + CSS
    state.py                  # session state helpers
    models.py                 # UI dataclasses (ChatMessage, LogEvent, etc.)
    orchestrator_client.py    # thin adapter to existing backend orchestrator
    components/
      __init__.py
      chat.py                 # chat rendering helpers
      trace.py                # streaming log panel
      results.py              # sql + grid cards
assets/
  td_logo.png                 # add TD logo image
```

Also add:
- `.streamlit/config.toml` (optional) for base theme settings (keep minimal)

---

## 5) Environment variables (standardize names)

**UI reads config only via `app.core.config.load_config()`** (your repo already has this).  
Ensure the UI does not invent new env names.

Expected (based on your earlier config loader fixes):
- `SEARCH_ENDPOINT`
- `OPENAI_ENDPOINT`
- `OPENAI_API_VERSION`
- `OPENAI_DEPLOYMENT`
- `SQLITE_PATH` (e.g., `local_data.db`)
- `MAX_SEARCH_DOCS` (default 50; UI overrides per user input)
- `MAX_RETRIES` (default 5)
- `DEBUG` (`true/false`)
- `SEND_RESULT_TO_GPT` (optional)

> **Important:** The UI should **not** require secrets in `.env` if using Managed Identity; it should only need endpoints + deployment names.

---

## 6) Data flow (high-level)

**UI**  
→ calls **OrchestratorClient.run_turn(user_text, chat_history, ui_options, event_cb)**  
→ orchestrator decides:
- metadata search (Azure AI Search)
- SQL generation (Azure OpenAI)
- SQL sanitize/validate
- execute SQL (SQLite now)
- post-processing: 0‑rows fallback, clarification question

**UI renders**
- live trace events (from `event_cb`)
- final assistant message + SQL + results grid

---

## 7) Required classes & method signatures (Copilot MUST follow these)

> **Note:** Only signatures + responsibilities. Copilot will implement the bodies.

### 7.1 `app/ui/models.py`

```python
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Literal

Role = Literal["user", "assistant", "system"]
EventType = Literal[
    "intent",
    "tool_call",
    "tool_result",
    "prompt_build",
    "sql_generated",
    "sql_sanitized",
    "sql_validated",
    "sql_executing",
    "sql_result",
    "fallback_0_rows",
    "clarification",
    "error",
    "info",
]

@dataclass
class ChatMessage:
    role: Role
    content: str
    ts_iso: str  # ISO timestamp string

@dataclass
class LogEvent:
    type: EventType
    message: str
    ts_iso: str  # ISO timestamp string
    data: Optional[Dict[str, Any]] = None

@dataclass
class UIOptions:
    max_rows: int
    execution_target: Literal["sqlite", "oracle"]  # oracle placeholder
    debug_enabled: bool
```

### 7.2 `app/ui/state.py`

```python
from typing import List
from .models import ChatMessage, LogEvent, UIOptions

def init_session_state() -> None:
    """Initialize Streamlit session state keys if missing."""

def get_chat_history() -> List[ChatMessage]:
    """Return chat history from session state."""

def append_chat_message(msg: ChatMessage) -> None:
    """Append message to chat history in session state."""

def clear_chat() -> None:
    """Clear chat + trace in session state."""

def get_trace_events() -> List[LogEvent]:
    """Return trace events in session state."""

def append_trace_event(ev: LogEvent) -> None:
    """Append a trace event to session state."""

def get_ui_options() -> UIOptions:
    """Return UIOptions based on sidebar controls and DEBUG flag."""
```

### 7.3 `app/ui/theme.py`

```python
def inject_td_theme() -> None:
    """
    Inject TD-styled CSS:
    - white background
    - TD green accents
    - clean rounded cards
    - better spacing/typography
    """
```

### 7.4 `app/ui/components/chat.py`

```python
from typing import List
from ..models import ChatMessage

def render_header() -> None:
    """Render TD header with logo + title + debug indicator (if enabled)."""

def render_chat_history(messages: List[ChatMessage]) -> None:
    """Render chat bubbles using Streamlit chat components."""

def chat_input_box() -> str | None:
    """
    Render the input box.
    Return user text when submitted, else None.
    Use st.chat_input for Enter-to-submit.
    """
```

### 7.5 `app/ui/components/trace.py`

```python
from typing import List
from ..models import LogEvent

def render_trace_panel(events: List[LogEvent], enabled: bool) -> None:
    """
    If enabled:
      - show a scrollable card with newest events at bottom
    Else:
      - show nothing (no empty space)
    """
```

### 7.6 `app/ui/components/results.py`

```python
from typing import Optional
import pandas as pd

def render_sql_card(sql: Optional[str]) -> None:
    """Expandable card showing SQL (monospace)."""

def render_results_grid(df: Optional[pd.DataFrame]) -> None:
    """Show results in a modern grid (st.dataframe) with reasonable height."""

def render_explanation(text: Optional[str]) -> None:
    """Short explanation card (keep business-friendly)."""

def render_error_card(err: str, debug_details: Optional[str], debug_enabled: bool) -> None:
    """User-friendly error + debug stack trace in expander when debug enabled."""
```

### 7.7 `app/ui/orchestrator_client.py` (thin adapter)

```python
from typing import Callable, List, Optional
import pandas as pd
from .models import ChatMessage, LogEvent, UIOptions

TraceCallback = Callable[[LogEvent], None]

class OrchestratorClient:
    def __init__(self) -> None:
        """Wire to existing app modules (config, orchestrator, sql service, search service)."""

    def run_turn(
        self,
        user_text: str,
        history: List[ChatMessage],
        options: UIOptions,
        trace_cb: Optional[TraceCallback] = None,
    ) -> "UIRunResult":
        """
        Run one user turn end-to-end.
        Must emit LogEvent via trace_cb at each major step.
        Must never raise raw exceptions to UI; return them in result.
        """

class UIRunResult:
    """
    Keep this as a simple container (dataclass recommended).
    Fields must include:
      - assistant_message: str
      - sql: Optional[str]
      - df: Optional[pd.DataFrame]
      - clarification_question: Optional[str]
      - error_message: Optional[str]
      - debug_details: Optional[str]
    """
```

> **Important integration rule:** OrchestratorClient should reuse your already-built backend logic instead of re-implementing tool calls in UI.

---

## 8) Streaming logs contract (how to emit trace)

In `OrchestratorClient.run_turn`, emit events like:

- `trace_cb(LogEvent(type="intent", message="Intent detected: ...", ...))`
- `trace_cb(LogEvent(type="tool_call", message="Searching metadata index meta_data_table", data={...}))`
- `trace_cb(LogEvent(type="tool_result", message="Found 3 candidate tables", data={...}))`
- `trace_cb(LogEvent(type="sql_generated", message="Generated SQL", data={"sql": "..."}))`
- `trace_cb(LogEvent(type="sql_executing", message="Executing SQL against SQLite", ...))`

UI will append them into session state and re-render the trace panel during execution.

---

## 9) UI entrypoint behavior (`app/ui/streamlit_app.py`)

**Must do:**
1) `inject_td_theme()`
2) `init_session_state()`
3) Render header + sidebar controls
4) Render chat history
5) Read `user_text = chat_input_box()`
6) If user_text submitted:
   - Append user message
   - Create a placeholder for assistant response (spinner)
   - Call `OrchestratorClient.run_turn(..., trace_cb=append_trace_event)`
   - Append assistant message (or clarification question)
   - Render SQL/results/explanation cards
   - If error: render error card

**Debug mode:**
- `debug_enabled = (DEBUG env is true) AND (user toggled debug ON)`
- If not debug mode: do not show trace panel, and do not show stack traces.

---

## 10) Acceptance criteria (definition of done)

- UI starts with: `streamlit run app/ui/streamlit_app.py`
- TD theme applied (white + green + logo)
- Chat works end-to-end with your orchestrator
- Logs stream shows step-by-step events while running (debug only)
- Results show as grid + SQL expander
- Clarifying question is displayed instead of hallucinated answers
- Keyboard submit works (Enter)
- No secrets committed; `.env` stays in `.gitignore`

---

## 11) Copilot execution steps (what Copilot should do now)

1) Create the folder/files in section 4.
2) Implement the class signatures exactly as in section 7.
3) Implement Streamlit UI rendering per section 9.
4) Wire `OrchestratorClient` to existing backend modules:
   - config loader
   - LLM SQL generation
   - Azure AI Search metadata lookup
   - SQL sanitize/validate/execute
   - 0‑rows fallback + clarification flows
5) Add minimal CSS in `theme.py` for TD look.
6) Provide a short README snippet with the run command.

**After implementation**, Copilot must run:
- `python -m app.main_cli "show me 10 rows from v_dlv_dep_prty_clr"` (backend sanity)
- `streamlit run app/ui/streamlit_app.py` (UI sanity)

---

## 12) Questions to answer ONLY if blocked (single question max)
If Copilot needs clarification, ask ONLY one:
- “Do you want the trace panel on the right sidebar or below the chat?”

(If not blocked, proceed with “below chat in debug mode”.)
