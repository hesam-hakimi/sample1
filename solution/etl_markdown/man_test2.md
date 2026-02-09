Implement the core NL→SQL pipeline WITHOUT tool-calling APIs.

Create:
- app/nl2sql.py

Design:
1) metadata plan step:
   - Send user question to LLM asking it to output STRICT JSON:
     {
       "metadata_queries": [
          {"purpose": "...", "sql": "SELECT ... FROM meta.... WHERE ..."}
       ]
     }
   - You will parse JSON using extract_json()
   - For each query:
     - validate_metadata_sql(query)
     - execute_query against SQL Server via app.db.execute_query
   - Collect results into a compact text context for the next step (limit rows per query to 50)

2) final SQL step:
   - Call LLM again with:
     - the user question
     - the metadata results context (tables/columns/relationships/terms)
   - Ask for STRICT JSON:
     {
       "sql": "SELECT ...",
       "explanation": "...",
       "assumptions": ["..."],
       "needs_confirmation": ["..."]
     }
   - validate_business_sql(sql)
   - return a dataclass-like dict {sql, explanation, assumptions, needs_confirmation}

Prompts must be deterministic:
- temperature=0
- include clear rules: “Do not invent tables/columns; only use what appears in metadata.”

Add tests:
- tests/test_nl2sql.py
  - Mock LLMClient.chat to return fixed JSON for plan + final
  - Mock execute_query to return small DataFrames
  - Ensure:
    - metadata queries validated
    - final SQL validated
    - output structure correct
    - invalid LLM SQL triggers ValueError
