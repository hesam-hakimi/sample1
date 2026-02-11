# Options & Long Poles (Aligned to Diagram Steps 1–11)

| Option ID | Option Name | What it is | Uses which steps? | Long Poles (time/risk) | Tactical workaround | Owner(s) |
|---|---|---|---|---|---|---|
| O1 | Synthetic dataset in KMAI | Create finance-like tables + 1k–2k rows | 4–11 (and optionally 1–3 if indexing metadata) | Credibility vs real data | Use realistic schema + joins; label synthetic | Naveen + Hesam |
| O2 | Manual export DevCZ/Synapse → upload | Download allowed dev data (IMSB only) then upload | 1,7,9–11 | Approval risk if confidential | Reduce scope; mask IDs | Saitha + Naveen |
| O3 | Leverage RW2/OCC/RW feed | Use RW data in account if allowed | 1,7,9–11 (plus semantic layer) | Access clarity + semantic layer | Start IMSB only | Saitha + Chakrapani |
| O4 | Direct connectivity DevSandbox → DevCZ/Synapse | Query dev sources directly | 4,8,9–11 | Network/identity approvals | Use O2 while waiting | Chakrapani + Saitha |
| O5 | Use TAP/AI2K2/Azure ML env | Use TAP env with data access | 4–11 | External OpenAI API may be blocked | Use internal endpoints | Chakrapani + Saitha + Naveen |
| O6 | Azure AI Search RAG | AI Search used for metadata retrieval | 1–8 (plus 11) | Index cap (3) | Delete/merge indexes | Naveen |
| O7 | Azure SQL + LLM | LLM generates SQL + execute on Azure SQL | 4,7–11 | SQL create privilege (9) | Use existing schema only | Chakrapani + Naveen |

## Shortlist suggestion (for demo by Tue)
- Immediate: O6 + O1 (works even without real data)
- Add “real-ish”: O2 or O3
- Strategic path after POC: O4 or O5 (+ TAP dev provisioning)
