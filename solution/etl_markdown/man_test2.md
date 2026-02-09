Add lightweight docs and a smoke runner.

Create:
- README.md with:
  - what this POC does
  - architecture diagram in text (bullet flow)
  - run instructions:
    1) run SQL scripts
    2) set env vars
    3) python app/main.py
  - security notes explaining the read-only guardrails and confirmation step

Create:
- scripts/smoke_test.py:
  - loads config
  - runs one NL→SQL request (mockable via env var SMOKE_FAKE_LLM=1)
  - if SMOKE_FAKE_LLM=1, bypass LLM and return a known safe SQL
  - otherwise calls the real pipeline

Add:
- tests/test_smoke_fake_llm.py verifying SMOKE_FAKE_LLM path works without Azure.
