# Prompt for Copilot/Codex: Build a Chat-First Text2SQL UI with Streaming Agent Logs (Streamlit)

## Context
You are working in the repo `text2sql_v2`. There is already:
- A CLI that can translate a user question into SQL, execute it, and print results.
- App code under `app/` including `app/core/orchestrator_facade.py` (used by the Streamlit UI).
- A Streamlit UI file at `app/ui/streamlit_app.py` (currently not matching requirements).

Your task: **Refactor / rebuild the Streamlit UI to be a true chat interface** where the **user and agent collaborate**. The UI must show:
- A **chat transcript** (user + assistant messages)
- A **streaming “activity log”** (progress updates like: “Deciding if search is needed…”, “Fetching from AI Search…”, “Reviewing table schema…”, “Generating SQL…”, “Executing SQL…”, “Summarizing results…”)
- The final assistant response must be produced by the LLM using the **SQL result data** (and optionally AI Search context) and be displayed in the chat.

> IMPORTANT: Do **NOT** invent new product features or UX beyond what’s written here. Do **NOT** redesign branding. Keep it clean, TD-like (white + green), but minimal. Your job is **implementation**, not product design.

---

## Non-negotiable behavior requirements

### 1) Chat-first collaboration
- The primary experience is a chat:
  - User types a message.
  - Agent replies in chat.
  - If the agent needs more info (missing table, ambiguous request), it asks follow-up questions in chat.
- The assistant message must include:
  - **Natural language answer**
  - **Generated SQL** (optional toggle)
  - **Result preview** (table/grid)
  - **Citations to data sources** (e.g., “SQL result”, “AI Search context”) in plain text

### 2) Streaming activity log (NOT chain-of-thought)
- Show a **streaming progress log** in the UI as the agent works.
- Do **NOT** expose raw chain-of-thought. Instead, expose **structured progress events**.
- Example events:
  - “Intent check: does this need AI Search?”
  - “AI Search: retrieving relevant docs…”
  - “Schema inspection: reading columns for v_dlv_dep_prty_clr…”
  - “SQL generation: drafting query…”
  - “SQL execution: running query (limit=50)…”
  - “Post-processing: formatting results…”
  - “LLM answer: summarizing output…”

### 3) Decide when AI Search is needed
- Some questions are pure SQL; some are not.
- Implement a deterministic **decision step**:
  - If question references policies/definitions/business meaning/documentation, or asks “what does X mean”, prefer AI Search.
  - If question is a direct data retrieval request (“show top 10…”, “count…”, “group by…”), AI Search usually not needed.
- The UI must show the decision and rationale in the activity log.

### 4) SQL results must go back to the LLM
- After SQL execution, the **dataset (rows + columns)** must be fed back into the LLM to generate the assistant’s final answer in chat.
- The user should see the assistant’s answer in chat, not just the raw table.

### 5) Strict structure: classes + methods
You must implement the following exact **public** structures (names, methods). You can add internal helpers, but do not rename these.

---

## Required Python structures

Create/ensure these modules exist:

### A) `app/core/chat_models.py`
Implement:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Dict, List

class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class EventType(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    STEP = "step"

@dataclass
class ChatMessage:
    role: Role
    content: str
    meta: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ActivityEvent:
    type: EventType
    message: str
    meta: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SqlResultPayload:
    sql: str
    columns: List[str]
    rows: List[List[Any]]
    row_count: int
    elapsed_ms: Optional[float] = None

@dataclass
class SearchPayload:
    used: bool
    query: str
    snippets: List[str] = field(default_factory=list)

@dataclass
class OrchestrationResult:
    assistant_message: ChatMessage
    generated_sql: Optional[str] = None
    sql_result: Optional[SqlResultPayload] = None
    search: Optional[SearchPayload] = None
    events: List[ActivityEvent] = field(default_factory=list)
```

### B) `app/core/activity_stream.py`
Implement:

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, List, Optional
from app.core.chat_models import ActivityEvent, EventType

EventSink = Callable[[ActivityEvent], None]

@dataclass
class ActivityStreamer:
    sink: EventSink

    def step(self, msg: str, **meta) -> None:
        self.sink(ActivityEvent(type=EventType.STEP, message=msg, meta=dict(meta)))

    def info(self, msg: str, **meta) -> None:
        self.sink(ActivityEvent(type=EventType.INFO, message=msg, meta=dict(meta)))

    def warn(self, msg: str, **meta) -> None:
        self.sink(ActivityEvent(type=EventType.WARNING, message=msg, meta=dict(meta)))

    def error(self, msg: str, **meta) -> None:
        self.sink(ActivityEvent(type=EventType.ERROR, message=msg, meta=dict(meta)))
```

### C) `app/core/search_decider.py`
Implement:

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class SearchDecision:
    use_search: bool
    reason: str

def decide_use_search(user_question: str) -> SearchDecision:
    """Deterministic heuristics (no LLM) to decide whether AI Search should be used."""
    ...
```

Rules:
- Must be deterministic (regex/keyword rules OK)
- Return `reason` suitable for showing in UI.

### D) `app/core/orchestrator_facade.py`
Expose **this exact function signature**:

```python
from __future__ import annotations
from typing import Optional
from app.core.chat_models import OrchestrationResult, ChatMessage
from app.core.activity_stream import ActivityStreamer

def run_chat_turn(
    *,
    user_message: ChatMessage,
    result_limit: int,
    show_sql: bool,
    streamer: ActivityStreamer,
) -> OrchestrationResult:
    """Runs exactly one chat turn end-to-end and returns a structured result."""
    ...
```

Inside `run_chat_turn`, implement these phases and emit events:
1. `decide_use_search`
2. If search: call existing AI Search client (whatever already exists in repo) and collect snippets
3. Schema inspection (if available): column list for target table(s) (reuse existing code you already have)
4. SQL generation (LLM call or existing generator)
5. SQL execution (existing SQLService)
6. LLM “final answer” generation using:
   - original question
   - generated SQL
   - sql result rows/columns (truncated safely)
   - search snippets (if any)
7. Return `OrchestrationResult` with assistant message and payloads

> Do not remove existing CLI logic. Reuse it where possible.

---

## Streamlit UI Requirements (`app/ui/streamlit_app.py`)

### Layout
- Left/top: App header (small TD logo if valid, otherwise fallback “TD” badge)
- Main: Chat transcript (like ChatGPT)
- Under/side: **Activity log** panel that updates during execution
- Below assistant message: optional SQL + results table with pagination/limit

### Chat mechanics
- Use `st.session_state` to store:
  - `messages: list[ChatMessage]`
  - `events: list[ActivityEvent]` (only for current turn or rolling)
- Use `st.chat_input` for message input.
- When user submits:
  - Append user message
  - Clear events
  - Create `ActivityStreamer` whose sink appends to session_state AND renders into a placeholder
  - Call `run_chat_turn(...)`
  - Append assistant message
  - Render results table (if any)

### Result rendering
- Use `st.dataframe` for results with `height` set and `use_container_width=True` (or Streamlit modern equivalent)
- Truncate very large results:
  - max rows displayed = `result_limit`
  - max columns displayed = all columns, but allow horizontal scroll
- Do not crash if no rows: show a helpful assistant message + keep log.

### Reliability / no import errors
- Fix `ModuleNotFoundError: No module named 'app'` by ensuring project root is on `sys.path` **at the top** of `streamlit_app.py`:
  - Detect repo root relative to this file and insert it into `sys.path` before importing `app.*`
- Do not add fragile absolute paths.

---

## Acceptance Criteria (must pass)
1. Running:
   - `python -m compileall app/ui/streamlit_app.py`
   - `.venv/bin/streamlit run app/ui/streamlit_app.py`
   must work without exceptions.
2. UI shows:
   - Chat transcript
   - Streaming activity log during run
3. A SQL question (e.g., “show me 10 rows from v_dlv_dep_prty_clr”) produces:
   - Generated SQL
   - Result grid
   - Assistant natural language summary in chat that uses the result
4. A non-SQL “definition/policy” question triggers:
   - AI Search usage decision = TRUE
   - Activity log includes “Fetching from AI Search…”
5. Code is clean, typed, and minimal.

---

## Implementation instructions (do this in order)
1. Create `app/core/chat_models.py`, `activity_stream.py`, `search_decider.py`
2. Refactor `app/core/orchestrator_facade.py` to implement `run_chat_turn(...)` while reusing existing code
3. Refactor `app/ui/streamlit_app.py` to:
   - bootstrap sys.path
   - implement chat UI + activity log
   - call `run_chat_turn`
4. Add lightweight unit tests (if repo has pytest):
   - test `decide_use_search` behavior with 6–8 examples
5. Provide a short summary of files changed

---

## Guardrails
- Do NOT add external heavy frameworks.
- Do NOT add a new UI framework; use Streamlit only.
- Do NOT hardcode credentials.
- Do NOT output chain-of-thought; only progress events.
- Keep the UI minimal and functional.

---

## Deliverables
- Updated/created Python files implementing the required structures.
- Updated Streamlit UI matching the requirements.
- Tests for `decide_use_search`.
