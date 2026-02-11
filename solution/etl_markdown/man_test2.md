| #      | What it represents                                                                                                                     |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| **1**  | **Ingest & chunk the source data** (e.g., Excel dataset and EDC content) into smaller “data chunks” suitable for search and retrieval. |
| **2**  | **Send each chunk to the embedding model** to convert it into a numeric vector (embedding) that captures meaning.                      |
| **3**  | **Store embeddings + chunk metadata** in the **vector database / Azure AI Search** (this becomes your searchable knowledge index).     |
| **4**  | **User asks a question** in the application (chat/UI).                                                                                 |
| **5**  | **AI Search returns the most relevant chunks** (top matches) back to the app based on similarity search.                               |
| **6**  | **App queries AI Search** (typically: embed the user question → run vector search → request top-k results).                            |
| **7**  | **App sends an augmented prompt to the LLM** (user question + retrieved chunks + instructions/guardrails).                             |
| **8**  | **LLM generates an output** (answer, explanation, or a SQL query / structured instruction depending on the app design).                |
| **9**  | **App executes the generated SQL / query** against the “production-ready” database (if your flow includes live data).                  |
| **10** | **Database returns results** to the app (rows, aggregates, KPI values, etc.).                                                          |
| **11** | **App sends the final response to the user** (often combining: LLM response + retrieved citations + live DB results).                  |
