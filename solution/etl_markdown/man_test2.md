Create a Gradio UI that:
- lets user chat (natural language)
- shows proposed SQL (not executed yet)
- requires explicit confirmation to run
- displays query result (DataFrame)

Create:
- app/ui.py:
  - Gradio Blocks with:
    - Chatbot
    - Textbox + Send button
    - SQL Code panel (read-only display)
    - “Run SQL” button
    - Results table (gr.Dataframe)
    - gr.State to store last proposed SQL + last explanation
  - send handler:
    - calls nl2sql.generate_sql(question)
    - updates chat + SQL panel but does NOT execute
  - run handler:
    - executes stored SQL via db.execute_query
    - shows DataFrame results
    - handle errors nicely (show error in chat)

Create:
- app/main.py:
  - launches the UI (gradio) with sensible defaults
  - reads config
  - has `if __name__ == "__main__": main()`

Add tests:
- tests/test_ui_logic.py:
  - Don’t launch Gradio server.
  - Unit-test the handler functions by calling them directly with mocks (LLM + DB).
