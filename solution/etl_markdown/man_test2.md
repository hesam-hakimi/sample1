You are working in THIS repo. Refactor the Gradio UI into a COMPLETE CHAT experience and update the backend so that:
1) The entire user experience is chat-only (no separate result grid panel).
2) When the user asks for data, we execute SQL and render the result INLINE in the chat as a markdown table + a short summary.
3) The LLM MUST have access to the returned data in subsequent turns (chat memory).
4) Must remain SAFE: do not execute destructive SQL; enforce validation; require confirmation for dbo.* queries.
5) Must work even when meta.* schema/tables are missing AND even when CREATE TABLE permission is denied.

Hard constraints:
- DO NOT use OpenAI Runner/Agent/Agents SDK.
- Use openai.AzureOpenAI with MSI token provider (ManagedIdentityCredential + get_bearer_token_provider).
- Tests must run without real SQL Server or Azure OpenAI (use mocks).
- Keep changes incremental and do not delete core modules (db.py, llm_client.py, sql_safety.py, nl2sql.py). You can refactor them, but keep them present.

========================================================
TARGET UI BEHAVIOR (Chat-only)
========================================================
UI contains:
- One gr.Chatbot that shows the conversation
- One textbox for user input + Send button
Optional: a tiny “DB status” message inside chat (as assistant message). No separate Dataframe component.

Conversation rules:
- On every user message, append it to conversation state (history).
- Assistant answers as a normal chat message.
- When data is retrieved from DB, append a TOOL message (role="tool") to the conversation state containing:
  - executed SQL (as a code block)
  - result markdown table (limited rows/cols)
  - result summary (row count, columns, simple stats if possible)
  - compact JSON sample (limited rows) for LLM context

Then call LLM again to produce the human-friendly explanation that references the tool output.
The assistant must NEVER hallucinate results not present in tool output.

========================================================
STATE MODEL (must be consistent)
========================================================
Create a new module: app/chat_types.py

Define:
- ChatRole = Literal["user","assistant","tool","system"]
- @dataclass ChatMessage:
    role: ChatRole
    content: str
    name: Optional[str] = None

State stored in gr.State:
- messages: list[ChatMessage]  # full history
- pending_sql: str             # "" if none
- pending_reason: str          # what needs confirmation
- last_sql: str                # last executed sql (for display/debug)
- last_result_compact: str     # compact json sample string (for LLM)
- meta_ready: bool             # computed lazily (optional)

DO NOT store DataFrame in state. Store rendered/compact strings only.

========================================================
FORMATTING RESULTS (inline chat)
========================================================
Create new module: app/formatting.py

Implement:
1) def df_to_markdown_table(df: pd.DataFrame, max_rows: int = 20, max_cols: int = 12) -> str
   - truncate to max_rows/max_cols
   - if empty df -> return "(no rows)"
   - return markdown table using pandas .to_markdown(index=False) if available,
     otherwise implement manual markdown generation (no extra deps).
2) def df_to_compact_json(df: pd.DataFrame, max_rows: int = 50, max_cols: int = 30) -> str
   - truncate rows/cols and return JSON string with records orientation
   - ensure it is small (limit)
3) def summarize_df(df: pd.DataFrame) -> str
   - include: row count, column list, and for numeric columns basic min/max if feasible

Add tests: tests/test_formatting.py
- verify row/col limits
- verify empty df formatting
- verify compact json row limit

========================================================
SAFETY & CONFIRMATION (must be strict)
========================================================
Update/ensure app/sql_safety.py has:
- is_read_only_select(sql) -> bool
- validate_metadata_sql(sql) -> None
- validate_business_sql(sql) -> None

Enforce:
- Reject if sql is None/"".
- Reject if contains ';', '--', '/*', '*/' anywhere.
- Reject DDL/DML keywords case-insensitive:
  INSERT UPDATE DELETE DROP ALTER CREATE TRUNCATE MERGE EXEC EXECUTE GRANT REVOKE DENY
- Allow only SELECT or WITH ... SELECT patterns.

Confirmation policy:
- ALWAYS require confirmation before executing any SQL referencing dbo.* tables.
- NO confirmation required for pure system catalog queries (sys.tables, INFORMATION_SCHEMA.*)
- NO confirmation required for metadata readiness checks (OBJECT_ID queries).
- Confirmation mechanism:
  - If SQL requires confirmation and no pending_sql exists:
    - store pending_sql
    - assistant asks: "I can run this query. Reply YES to run, or NO to cancel."
  - If pending_sql exists:
    - if user says yes -> execute
    - if user says no -> clear pending_sql and respond "Canceled."
    - otherwise -> ask again (do not execute)

Create new module app/confirm.py:
- detect_yes_no(text: str) -> Optional[bool]
  - accepts: yes/y/ok/sure/run it (true), no/n/cancel (false)
  - case-insensitive, trimmed
Add tests: tests/test_confirm.py

========================================================
DB LAYER updates (avoid crashing)
========================================================
Update app/db.py:
- ensure connect is lazy; do not connect at import time.
- add:
  def metadata_ready() -> tuple[bool, list[str]]:
    checks existence:
      schema meta and tables meta.Tables, meta.Columns, meta.Relationships, meta.BusinessTerms
    Use:
      SELECT CASE WHEN SCHEMA_ID('meta') IS NULL THEN 0 ELSE 1 END AS has_meta_schema
      SELECT OBJECT_ID('meta.Tables') AS obj
    Return missing list.

- add:
  def list_all_tables() -> pd.DataFrame:
    returns schema_name, table_name from sys.tables/sys.schemas
- add:
  def list_columns(schema: str, table: str) -> pd.DataFrame:
    uses sys.columns/sys.types joins
- improve error mapping:
  - login timeout -> "Cannot reach SQL Server... check SQL_SERVER and firewall/VNet"
  - permission denied create table -> show a helpful message
Keep execute_query(max_rows enforced) and query timeout.

Add tests with mocks: tests/test_db_errors.py and tests/test_db_meta_ready.py

========================================================
LLM CLIENT (must accept conversation)
========================================================
Update app/llm_client.py:
- LLMClient.chat must accept messages list:
  def chat_messages(messages: list[dict], temperature=0, max_tokens=800) -> str
- Keep extract_json robust.

We will build messages for the API as:
- system message with rules
- then conversation history:
  - user/assistant/tool messages appended in order
Tool messages are passed as role="user" or role="system"? We do NOT have tool-role support in all clients.
Do this:
- In API request, represent tool messages as role="system" with prefix "TOOL_RESULT:"
or role="user" with prefix "TOOL_RESULT:".
Choose one consistent approach and document it.

Rules for tool messages:
- include compact json and summary; MUST be included in the prompt so the model can answer follow-ups.

Add tests: tests/test_llm_client_messages.py verifying we pass messages in correct structure (mock client).

========================================================
NL2SQL orchestration (2-stage with tool message)
========================================================
Update app/nl2sql.py to become chat-context aware.

Create:
- def handle_user_turn(messages: list[ChatMessage], user_text: str, pending_sql: str) -> tuple[new_messages, pending_sql, last_sql, last_result_compact]

Algorithm:
1) append user message
2) if pending_sql is not empty:
   - run detect_yes_no(user_text)
   - if yes: execute pending_sql (validate_business_sql first) -> df
       - create tool message with SQL + markdown + summary + compact json
       - append tool message
       - call LLM to explain results using conversation including tool message
       - append assistant message
       - clear pending_sql
       - return
   - if no: append assistant "Canceled." clear pending_sql return
   - else: append assistant "Please reply YES or NO." return

3) If no pending_sql:
   - if greeting/smalltalk: append assistant greeting (NO DB)
   - else:
       - call db.metadata_ready()
         a) if user asks "list tables" or similar:
             - run db.list_all_tables() and build tool message and assistant response (no LLM required or optionally LLM summary)
         b) if meta not ready:
             - append assistant explaining metadata not initialized + suggest using list tables or specify table names; do not crash.
             - return
       - If meta ready:
           Stage A: Ask LLM to output STRICT JSON plan:
             {"metadata_queries":[{"purpose":"...","sql":"SELECT ... FROM meta...."}]}
           Validate each query with validate_metadata_sql; execute (max_rows=50 per query).
           Build a metadata context string from results (markdown + compact json).
           Stage B: Ask LLM to output STRICT JSON:
             {"sql":"SELECT ...", "explanation":"...", "assumptions":[...], "needs_confirmation":[...]}
           Validate business SQL with validate_business_sql.
           If needs_confirmation not empty OR policy requires confirmation:
              set pending_sql = sql
              append assistant message containing explanation + the SQL in code block + ask for YES/NO.
              return
           Else (should be rare): execute sql, append tool message, call LLM to explain results, append assistant.

Important:
- Always enforce limits and never include huge tables in LLM context.
- Always catch exceptions and present user-friendly error in assistant message.

Add tests: tests/test_nl2sql_chat_flow.py
- greeting -> no db called
- list tables -> sys catalog called, tool message appended, no crash
- meta missing -> assistant explains and no LLM plan queries attempted
- pending_sql yes -> executes, tool message appended, assistant follow-up appended
All with mocks.

========================================================
UI implementation (Gradio)
========================================================
Update app/ui.py to use ONLY:
- Chatbot
- Textbox
- Send button
- gr.State variables for messages + pending_sql + last_sql + last_result_compact

Implementation details:
- Convert messages list to gr.Chatbot format: list[tuple[str|None, str|None]]
  Display tool messages as assistant messages with a prefix like:
  "**[Data]** ..." so user sees it in chat.
- On send:
  call nl2sql.handle_user_turn(...)
  update chatbot + clear textbox
- Remove old panels (Proposed SQL grid, results dataframe panel, extra buttons).
Optionally keep a single small button “List Tables” that simply sends a user turn equivalent.

Add tests: tests/test_ui_handlers.py
- ensure send handler returns expected chatbot entries and state updates.

========================================================
Documentation
========================================================
Update README.md:
- explain chat-only flow
- explain YES/NO confirmation
- explain metadata prerequisite and what happens if meta not ready
- explain permissions limitation (CREATE TABLE denied) and that app can still list tables and run queries if meta exists

========================================================
DELIVERABLE
========================================================
Make the changes in code. Provide full contents of each modified/new file.

Before finishing, ensure:
- python -m app.main works
- pytest -q passes
- no code path attempts CREATE TABLE automatically
- results are shown in the chat and then included in the next LLM call via tool message

Do NOT leave TODOs. Implement fully.
