Refactor the ETL VS Code extension to improve readability by splitting the 300+line etlAssistantHandler + extension wiring into smaller modules, while keeping full backward compatibility.

Hard requirements:
- Do NOT change command IDs, chat participant ID, settings keys, or user-visible behavior.
- Refactor in small steps with tests passing after each step.
- Follow Meta_Testing_Strategy_For_Copilot.md for correct VS Code test host setup.

Plan:
1) Extract pure intent detection into src/chat/intent.ts (no vscode import). Add unit tests for it.
2) Extract context building into src/chat/contextBuilder.ts. Add integration test that it reads active editor and loads src/context_files.
3) Split handler into:
   - src/chat/handlers/applyEditHandler.ts
   - src/chat/handlers/qnaHandler.ts
   Keep src/chat/etlAssistantHandler.ts as a thin orchestrator.
4) Create core modules:
   - src/core/logger.ts
   - src/core/settings.ts
   - src/core/pythonRunner.ts (if not already)
5) Make src/extension.ts minimal wiring only.

After each step:
- run npm test
- confirm behavior parity with existing tests
- summarize what changed.

Verification:
- existing tests still pass
- new tests prove apply edits still work and non-apply QnA never edits.
