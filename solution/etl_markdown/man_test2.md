We get this Gradio runtime error in the chat-only UI:

"Data incompatible with messages format. Each message should be a dictionary with 'role' and 'content' keys or a ChatMessage object."

Root cause:
We are using gr.Chatbot(type="messages") but we are passing our own app.chat_types.ChatMessage dataclass instances (or other incompatible structures) to the Gradio Chatbot update.

Fix requirements:
1) Keep our internal message dataclass for state if we want, BUT the value sent to the Gradio Chatbot MUST always be:
   List[Dict[str,str]] with keys exactly: role, content
   Example: {"role":"user","content":"..."}.

2) Implement a single conversion function in app/ui.py (or a helper module):
   def to_gradio_messages(app_messages) -> list[dict]:
      - map roles:
        - "user" -> "user"
        - "assistant" -> "assistant"
        - "tool" -> "assistant" (prefix content with "**[DATA]**" or "**[TOOL]**")
        - "system" -> "assistant" (or drop, but prefer mapping to assistant for visibility)
      - ensure content is always a string (never None)
      - return list of {"role": ..., "content": ...}

3) Ensure gr.Chatbot is defined consistently:
   - If using dict messages, keep: gr.Chatbot(type="messages")
   - Then every handler must return the chatbot value as list[{"role","content"}]
   - Do NOT return list of tuples or list of dataclass objects to the chatbot component.

4) Update all UI handlers in app/ui.py:
   - send handler
   - list tables handler
   - any init/check buttons
   so they return:
     (chatbot_messages_as_dicts, updated_state...)

5) IMPORTANT: If we accidentally named our dataclass "ChatMessage", rename it to avoid confusion:
   - In app/chat_types.py rename ChatMessage -> AppChatMessage
   - Update imports accordingly
   This prevents mixing it up with Gradio’s ChatMessage type.

6) Add a regression test:
   Create tests/test_gradio_message_format.py:
   - call the send handler (with mocked nl2sql) and assert the first output (chatbot) is a list of dicts
   - assert each dict has keys role/content and both values are strings

Acceptance criteria:
- App loads without the red “Error” bubbles.
- Clicking Send/List Tables updates the chat successfully.
- pytest -q passes.
Return full updated contents for any modified/new files.
