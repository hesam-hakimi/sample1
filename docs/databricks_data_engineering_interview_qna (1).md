# Databricks Data Engineering Interview (30 minutes) — Question Bank + Answer Key

This pack is designed for an **intermediate → advanced** Databricks Data Engineering interview you can run in ~30 minutes.

---

## Suggested 30‑minute structure

- **2 min**: Candidate intro (recent projects + what they owned end‑to‑end)
- **20 min**: Technical Q&A (pick ~8 questions below)
- **6–8 min**: Deep‑dive follow‑ups on 1–2 topics (performance + Delta/streaming)
- **2 min**: Wrap (questions from candidate, next steps)

> Tip: Don’t try to ask everything. Pick questions based on the role (batch vs streaming, Lakehouse vs warehouse-heavy, governance needs, etc.).

---

## Scoring rubric (quick)

Score each question **0–2**:
- **0** = vague / incorrect / hand‑wavy
- **1** = mostly correct, missing important details
- **2** = correct + practical details + trade‑offs + Databricks specifics

**Hire signals**
- Can explain Spark execution + common perf pitfalls
- Understands Delta Lake transactional guarantees + upsert patterns
- Can reason about partitions/files/OPTIMIZE/ZORDER and cost/perf trade‑offs
- Practical governance (Unity Catalog), pipeline reliability, and debugging ability

---

# Core Questions (intermediate → advanced)

## Q1) Explain what happens when you run a Spark job on Databricks (high level).
**Looking for**
- Driver vs executors, DAG, stages, tasks, shuffles, lazy evaluation
- Actions vs transformations, narrow vs wide dependencies

**Strong answer (key points)**
- Transformations build a **logical plan**; Spark optimizes into a **physical plan**.
- An **action** triggers execution. Spark builds a **DAG**, splits into **stages** at shuffle boundaries, and runs **tasks** per partition on executors.
- **Shuffles** move data across the network; they dominate time/cost if large.
- Databricks runtime can add optimizations (e.g., AQE, Photon depending on cluster/type).

**Good follow‑ups**
- What causes a shuffle? (joins, groupBy, distinct, repartition, sort)
- How to see the plan? (`df.explain(True)`, Spark UI, event logs)

**Red flags**
- Thinks Spark “executes line by line” or can’t describe driver/executors.

---

## Q2) Broadcast join vs shuffle join: when and why?
**Looking for**
- Join strategy selection, thresholds, skew, memory constraints

**Strong answer**
- Broadcast join sends the smaller table to all executors, avoiding shuffle on that side.
- Use when the dimension table is **small enough** to fit in memory per executor.
- Enable/force via hints (`broadcast(df)`) and tune `spark.sql.autoBroadcastJoinThreshold`.
- For skewed data, combine strategies: broadcast + filter early, salting, or AQE skew join handling.

**Follow‑ups**
- How to detect skew? (Spark UI, task time variance, skewed keys)
- What if broadcast OOMs? (reduce columns, filter first, raise memory, disable broadcast)

---

## Q3) Partitioning strategy for Delta tables: what do you choose and why?
**Looking for**
- Partition pruning, cardinality, file sizes, query patterns

**Strong answer**
- Partition on columns frequently used in filters with **moderate cardinality** (e.g., date).
- Too many partitions = many small files + metadata overhead; too few = poor pruning.
- Prefer **date** (day/month) for time-series; avoid high-cardinality IDs.
- Pair partitions with `OPTIMIZE` and optionally `ZORDER BY` for common predicates.
- Monitor file size (often target ~128–1024MB depending on workload).

**Follow‑ups**
- How to fix small files? (`OPTIMIZE`, auto optimize, compaction jobs)
- Partition vs ZORDER vs clustering (Databricks features)

**Red flags**
- “Always partition by customer_id” without considering cardinality.

---

## Q4) Delta Lake ACID and concurrency: what guarantees do you get?
**Looking for**
- Transaction log, optimistic concurrency control, atomic commits

**Strong answer**
- Delta uses a **transaction log** (JSON/Parquet) to provide ACID on files in object storage.
- Writes are **atomic**; readers see a consistent snapshot (snapshot isolation).
- Concurrency via **optimistic concurrency control**; conflicting writes can fail and need retry patterns.
- Supports schema evolution (controlled) and time travel.

**Follow‑ups**
- When does a MERGE conflict happen? (overlapping files/rows updated concurrently)
- How to reduce contention? (partitioning by write keys, micro-batching, job coordination)

---

## Q5) MERGE INTO in Delta: best practices for upserts (SCD-like patterns).
**Looking for**
- Match keys, dedup incoming batch, idempotency, partition pruning

**Strong answer**
- Ensure the source is **deduplicated on the merge key** (one row per key) to avoid ambiguous updates.
- Use deterministic keys, and include a watermark/ingestion timestamp for idempotency.
- Optimize merge performance by:
  - pruning target via partitions (e.g., merge only recent dates),
  - using `OPTIMIZE` / ZORDER on merge keys where appropriate,
  - avoiding merging tiny batches too frequently.

**Follow‑ups**
- How do you handle late arriving updates? (watermark, CDF, reprocessing window)
- How to implement SCD2? (valid_from/valid_to/is_current logic)

**Red flags**
- Doesn’t mention dedup or idempotency.

---

## Q6) Change Data Feed (CDF): what is it and when would you use it?
**Looking for**
- Incremental processing patterns

**Strong answer**
- Delta CDF records row-level changes (inserts/updates/deletes) between versions.
- Great for incremental downstream pipelines without scanning full tables.
- Needs to be enabled and then consumers read changes by version/timestamp.

**Follow‑ups**
- CDF vs CDC from source? (CDF is table-level within Delta)
- How would you reprocess? (time travel, version checkpoints)

---

## Q7) Structured Streaming on Databricks: how do you build reliable pipelines?
**Looking for**
- Exactly-once semantics, checkpoints, watermarks, output modes

**Strong answer**
- Use **checkpointing** for state and progress; define **watermarks** for late data handling.
- Exactly-once is achievable with idempotent sinks like Delta + proper checkpointing.
- Choose output mode (append/update/complete) based on aggregation and sink.
- Monitor with Streaming UI; handle schema changes carefully (Auto Loader options).

**Follow‑ups**
- What causes duplicates? (replays without idempotency, non-deterministic ops)
- When to use Auto Loader? (incremental file discovery, schema inference/evolution)

---

## Q8) Auto Loader vs COPY INTO vs regular file reads: how do you decide?
**Looking for**
- File ingestion at scale, incremental discovery, operational simplicity

**Strong answer**
- **Auto Loader** is for scalable incremental ingestion of files with streaming semantics, notifications, schema evolution.
- **COPY INTO** is simple SQL-based ingestion, good for batch loads, less custom logic.
- Regular reads are fine for small/controlled datasets but can struggle at scale for discovery.

**Follow‑ups**
- How to deal with schema drift? (schema hints, rescue column, evolution policy)
- How to prevent reprocessing? (checkpoints, file tracking, ingestion metadata)

---

## Q9) Databricks performance: a job is slow. What’s your debugging checklist?
**Looking for**
- Spark UI, explain plans, data skew, shuffle, I/O, cluster sizing

**Strong answer**
1. Check **Spark UI**: stages, shuffle read/write, skewed tasks, spill, GC.
2. Review `df.explain(True)` / SQL query plan: join strategy, filters pushed down, partition pruning.
3. Validate file layout: small files, partitioning, stats, OPTIMIZE.
4. Look at cluster: executor count, memory, CPU, autoscaling, Photon.
5. Apply fixes: broadcast join, reduce shuffle, filter earlier, cache selective, tune partitions, OPTIMIZE/ZORDER.

**Follow‑ups**
- What’s your approach to tuning `spark.sql.shuffle.partitions`?
- When do you cache, and what are the risks?

---

## Q10) Data quality: how do you enforce and monitor it in Databricks?
**Looking for**
- Expectations, constraints, quarantine patterns, metrics

**Strong answer**
- Use **expectations** (e.g., in Delta Live Tables) or custom validation steps.
- Separate Bronze/Silver/Gold; quarantine bad records with reason codes.
- Track metrics: null rates, duplicates, referential integrity, freshness.
- Alerts and dashboards for pipeline SLAs (job status + data checks).

**Follow‑ups**
- How do you handle late-arriving reference data? (backfills, reprocessing)
- What checks are “blocking” vs “non-blocking”?

---

## Q11) Unity Catalog governance: what does it give you?
**Looking for**
- Central catalog, fine-grained permissions, lineage, auditing

**Strong answer**
- Centralized **data & AI governance**: catalogs/schemas/tables, permissions via grants, data masking/row filters (where applicable), lineage, audit logs.
- Separates storage credentials/external locations, improves access control vs legacy workspace-local metastore.

**Follow‑ups**
- External locations + storage credentials: why are they important?
- How to grant least privilege for a team?

---

## Q12) Orchestration and reliability: what’s your pattern for production pipelines?
**Looking for**
- Job design, idempotency, retries, backfills, observability

**Strong answer**
- Parameterized jobs, environment configs, secrets in Key Vault.
- Idempotent writes (Delta merges or overwrite partitions), retry-safe logic.
- Clear SLAs/alerts, structured logging, lineage, and runbooks.
- Backfill strategy: rerun for date ranges, rebuild gold from silver, etc.

**Follow‑ups**
- How do you avoid partial writes? (atomic commits, staging, transaction patterns)
- How do you manage schema changes safely?

---

# Advanced “if time” questions (pick 1–2)

## A1) Explain Adaptive Query Execution (AQE). What does it change?
**Key points**
- Spark can adjust join strategy, shuffle partitions, and handle skew at runtime using stats.
- Helps reduce shuffles and optimize partition sizes after seeing real data.

## A2) Photon: when does it help and when might it not?
**Key points**
- Vectorized engine that can speed SQL/DataFrame workloads.
- Biggest wins in SQL-heavy, scan/aggregation workloads; depends on runtime, operators, data format.

## A3) How do you handle incremental loads from a mutable source?
**Key points**
- Watermark columns, change tracking (CDC/CDF), late data window, dedup by key+updated_at.
- Idempotent merges; maintain checkpoints.

---

# Quick SQL round (2–3 minutes)

## SQL1) Find the latest record per customer (dedupe by updated_at)
**Expected solution**
- Window function: `row_number() over (partition by customer_id order by updated_at desc)` then filter `rn=1`.

## SQL2) Rolling 7-day revenue per day
**Expected solution**
- Window frame: `sum(revenue) over (order by day rows between 6 preceding and current row)` (or range interval where supported)

---

## Notes for interviewer
- Ask for **trade‑offs**: “When would you *not* do this?”
- Ask for **what they’d check** in Spark UI and **why**.
- Prefer **one deep performance debugging** over many shallow questions.

