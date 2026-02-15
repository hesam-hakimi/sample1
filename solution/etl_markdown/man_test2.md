# Copilot Prompt — Add Minimal Agent Smoke Test (no framework)

Create a new file: `scripts/agent_smoke_test.py`

Paste the following code exactly. Do NOT change existing files.

```python
"""
Minimal 'agent' smoke test (no agentic frameworks).
Goal: prove the loop works: plan -> tool -> observe -> next step, with streaming logs.

Run:
  /app1/tag5916/projects/text2sql_v2/.venv/bin/python scripts/agent_smoke_test.py "show me 10 rows from v_dlv_dep_prty_clr"

Optional env:
  DRY_RUN=true   # default true (no LLM call)
  MAX_STEPS=5    # default 5
"""

from __future__ import annotations

import os
import re
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

# Optional .env loading (safe if python-dotenv is not installed)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


@dataclass
class AgentDecision:
    action: str  # "tool" | "clarify" | "final"
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}

    def register(self, name: str, fn: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self._tools[name] = fn

    def call(self, name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        return self._tools[name](tool_input)


class SimpleAgent:
    """
    A tiny agent that decides between tools by rules (DRY_RUN) or by LLM later.
    For now, we keep it dependency-light so it works in restricted environments.
    """

    def __init__(self, tools: ToolRegistry) -> None:
        self.tools = tools

    def log(self, text: str) -> None:
        # stream-style logs
        print(f"[agent] {text}", flush=True)

    def plan(self, user_text: str, last_observation: Optional[Dict[str, Any]]) -> AgentDecision:
        """
        Decision policy:
          - If user asks ambiguous request, ask clarification.
          - If user mentions "metadata" or "relationship", call search tool.
          - Else assume SQL tool.
        """
        # Example clarification trigger (extend later)
        if len(user_text.strip()) < 4:
            return AgentDecision(action="clarify", message="Can you rephrase your question with more detail?")

        t = user_text.lower()

        if any(k in t for k in ["metadata", "meta data", "relationship", "fields", "table info", "schema"]):
            return AgentDecision(
                action="tool",
                tool_name="search_metadata",
                tool_input={"query": user_text, "top_k": 5},
            )

        # Default: go SQL
        return AgentDecision(
            action="tool",
            tool_name="run_sql",
            tool_input={"nl_query": user_text, "limit": 10},
        )

    def run(self, user_text: str, max_steps: int = 5) -> Dict[str, Any]:
        self.log("Starting agent loop")
        observation: Optional[Dict[str, Any]] = None

        for step in range(1, max_steps + 1):
            self.log(f"Step {step}/{max_steps}: planning")
            decision = self.plan(user_text, observation)

            if decision.action == "clarify":
                self.log("Need clarification")
                return {"status": "clarify", "message": decision.message}

            if decision.action == "final":
                self.log("Final answer ready")
                return {"status": "final", "message": decision.message, "observation": observation}

            # Tool call
            assert decision.tool_name and decision.tool_input is not None
            self.log(f"Calling tool: {decision.tool_name} with {decision.tool_input}")

            try:
                observation = self.tools.call(decision.tool_name, decision.tool_input)
                self.log(f"Tool observation keys: {list(observation.keys())}")
            except Exception as e:
                self.log(f"Tool error: {type(e).__name__}: {e}")
                return {"status": "error", "error_type": type(e).__name__, "error": str(e)}

            # Simple stop condition for smoke test
            if observation.get("done") is True:
                self.log("Tool signaled done=True, finishing")
                return {"status": "final", "message": observation.get("message", "Done"), "observation": observation}

            # Otherwise continue loop (in real agent you'd feed observation back to LLM)
            time.sleep(0.05)

        self.log("Reached max steps without final answer")
        return {"status": "max_steps", "observation": observation}


# -------------------------
# Stub tools (replace later)
# -------------------------

def tool_search_metadata(inp: Dict[str, Any]) -> Dict[str, Any]:
    q = inp.get("query", "")
    top_k = int(inp.get("top_k", 5))
    # Stub response (replace with Azure AI Search query)
    return {
        "done": True,
        "message": f"(stub) searched metadata for: {q}",
        "top_k": top_k,
        "results": [
            {"id": "meta_data_field:demo", "score": 1.0, "text": "Field metadata result (stub)"},
        ],
    }


def tool_run_sql(inp: Dict[str, Any]) -> Dict[str, Any]:
    nlq = inp.get("nl_query", "")
    limit = int(inp.get("limit", 10))

    # Extremely naive NL->SQL for smoke test
    # Replace with your real LLM->SQL + sqlite execution later.
    if "from" in nlq.lower():
        sql = nlq
    else:
        # Try to infer a table name token
        m = re.search(r"(v_[a-z0-9_]+)", nlq.lower())
        table = m.group(1) if m else "v_dlv_dep_prty_clr"
        sql = f"SELECT * FROM {table} LIMIT {limit};"

    return {
        "done": True,
        "message": f"(stub) would execute SQL: {sql}",
        "sql": sql,
        "rows_preview": [],
    }


def main() -> None:
    import sys

    user_text = sys.argv[1] if len(sys.argv) > 1 else "show me 10 rows from v_dlv_dep_prty_clr"
    max_steps = int(os.getenv("MAX_STEPS", "5"))

    tools = ToolRegistry()
    tools.register("search_metadata", tool_search_metadata)
    tools.register("run_sql", tool_run_sql)

    agent = SimpleAgent(tools)
    result = agent.run(user_text, max_steps=max_steps)

    print("\n=== RESULT ===")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
