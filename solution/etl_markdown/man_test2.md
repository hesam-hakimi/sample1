# Options Matrix — Strategic vs Tactical

| Option ID | Option | Description | Strategic/Tactical | Pros | Cons/Risks | Dependencies | Current Recommendation |
|---|---|---|---|---|---|---|---|
| A | Connect DevSandbox → Synapse/SRZ/Dev* | Direct query on real dev data | Strategic | Realistic demo, less copying | Access/network approvals may take time | Connectivity, firewall, creds | Explore in parallel |
| B | Replicate/copy subset of IM/SP/SD dev data into DevSandbox | Curated dataset for POC | Tactical → bridge | Fast if allowed; stable | Data movement approval; freshness | Export process, storage, masking | Fallback if A slips |
| C | Azure AI Search + OpenAI | Use search index for retrieval + grounding | Tactical/Strategic | Great for docs + schema assist | Index cap (50) reached | Index quota/cleanup | Viable if blocker resolved |
| D | Azure SQL + LLM (Text-to-SQL) | LLM generates SQL + executes on Azure SQL | Tactical/Strategic | Very direct POC path | SQL user lacks create privileges | DBA grant / alt schema | Viable with privilege fix |
| E | File-based tables (CSV/Parquet) + SQL engine | Store extracts in files; query via engine | Tactical | Avoid DB permissions | More plumbing; data drift | Storage + query engine | Consider if DB blocked |
| F | Manual schema prompt pack | Hardcode schema/definitions for POC | Tactical | Very fast to start | Limited coverage; brittle | Someone to curate | Use immediately for skeleton |
