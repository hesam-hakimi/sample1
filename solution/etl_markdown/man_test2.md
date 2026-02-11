# Blockers / Risks / Decisions Register (Aligned to Diagram Steps 1–11)

## Diagram Legend (use these exact meanings)
| Step # | Meaning |
|---:|---|
| 1 | Ingest & chunk source content (metadata/docs/schema or approved data extracts) |
| 2 | Send chunks to embedding model |
| 3 | Store embeddings + chunk metadata in Azure AI Search (vector DB) |
| 4 | User asks a question (UI/chat) |
| 5 | AI Search returns relevant chunks (top matches) |
| 6 | App queries AI Search (vector search request) |
| 7 | App sends augmented prompt to LLM (question + retrieved chunks + guardrails) |
| 8 | LLM generates output (answer and/or SQL) |
| 9 | App executes generated SQL on target database (if enabled) |
| 10 | Database returns results to app |
| 11 | App returns final response to user (summary + citations + results) |

---

## Register
| ID | Type | Related Option(s) | Step # | Issue | Impact | Workaround (tactical) | Strategic Fix | Reach out to | Reached out? (Y/N) | Response / Acknowledged | Owner | Status (🟢🟡🔴) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B1 | Blocker | O6 | 3 | AI Search index limit (50) | Can’t create new indexes | Delete/merge unused; reuse existing index | Quota increase + redesign indexing | AI Search platform owner |  |  | Naveen | 🔴 |
| B2 | Blocker | O7 | 9 | SQL user cannot create objects | Blocks schema/views/staging | Use existing schema only | Dedicated schema / minimal create rights | DBA / platform |  |  | Chakrapani + Naveen | 🔴 |
| B3 | Risk/Decision | O2/O3 | 1,9 | Confidential identifiers in extracted data | Approval required; delays | IMSB only + mask/remove IDs | Governance-approved pipeline | Data governance / source owner |  |  | Saitha | 🟡 |
| B4 | Risk | O4 | 9 | No direct connectivity to DevCZ/Synapse | Direct query not possible | Manual export/import (O2) | Enable network/identity | Network/platform team |  |  | Chakrapani + Saitha | 🟡/🔴 |
| B5 | Risk | O5 | 7–9 | External OpenAI API blocked in TAP env | Architecture constraints | Use internal LLM endpoints | Partner with TAP team | TAP/Layer6 team |  |  | Chakrapani + Saitha | 🟡 |
| B6 | Clarity Gap | All | 8→9 | Need validation/confirmation before executing SQL | Risk of wrong/unsafe query | Add “SQL validate + user confirm” gate | Governance policy enforcement | App owner |  |  | Naveen | 🟡 |
| D1 | Decision | All | N/A | Decide demo path (Tue target) | Drives timeline | Start O6+O1 now | Move to O2/O4/O5 as strategic | Praveen + Chakrapani |  |  | Saitha | 🟡 |
| D2 | Decision | Post-POC | N/A | Provision TAP-supported dev environment | Needed after POC | Start request in parallel | TAP intake + landing zone | Chakrapani + Saitha |  |  | Chakrapani | 🟡 |
