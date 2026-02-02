# Databricks Live Coding Exercise (Notebook‑friendly) — PySpark + SQL (20–30 minutes)

Use this during the interview to assess practical skills: reading data, transformations, Delta writes, and SQL reasoning.

You can paste this into a Databricks notebook (recommended: **one cell per section**).  
Candidate can choose PySpark or SQL where appropriate.

---

## What you are testing

- PySpark DataFrame fluency (select/withColumn/join/window)
- Data quality + dedup logic
- Delta Lake write patterns (partitioning, merge/upsert)
- Basic performance awareness (explain plan, shuffle reduction)
- SQL skills (window functions, aggregation)

---

## Dataset setup (synthetic, no external files needed)

### Cell 1 — Create sample data (PySpark)

```python
from pyspark.sql import functions as F, Window as W

spark.conf.set("spark.sql.shuffle.partitions", "64")

# Customers (dimension)
customers = (
    spark.range(1, 5001).withColumnRenamed("id", "customer_id")
    .withColumn("country", F.expr("element_at(array('CA','US','GB','DE','FR'), int(rand()*5)+1)"))
    .withColumn("segment", F.expr("element_at(array('retail','smb','enterprise'), int(rand()*3)+1)"))
    .withColumn("created_at", F.current_timestamp())
)

# Orders (facts) - includes duplicates and updates
orders_raw = (
    spark.range(1, 200001).withColumnRenamed("id", "order_id")
    .withColumn("customer_id", (F.rand()*5000 + 1).cast("int"))
    .withColumn("order_ts", F.expr("timestampadd(minute, -int(rand()*60*24*30), current_timestamp())"))
    .withColumn("amount", F.round(F.rand()*500 + 5, 2))
    .withColumn("status", F.expr("element_at(array('NEW','PAID','CANCELLED','REFUNDED'), int(rand()*4)+1)"))
    .withColumn("updated_at", F.expr("timestampadd(minute, int(rand()*120), order_ts)"))
)

# Introduce duplicates: same order_id appears multiple times with different updated_at
dupes = orders_raw.sample(withReplacement=False, fraction=0.03, seed=7) \
    .withColumn("updated_at", F.expr("timestampadd(minute, 30, updated_at)")) \
    .withColumn("status", F.lit("PAID"))

orders_raw = orders_raw.unionByName(dupes)

# A nested "events" JSON-like column to test parsing
orders_events = orders_raw.select(
    "order_id", "customer_id", "order_ts", "amount", "status", "updated_at",
    F.to_json(F.struct(
        F.col("status").alias("event_type"),
        F.col("updated_at").alias("event_ts"),
        F.struct(
            F.expr("element_at(array('web','ios','android','store'), int(rand()*4)+1)").alias("channel"),
            F.expr("element_at(array('promo','none','vip'), int(rand()*3)+1)").alias("campaign")
        ).alias("metadata")
    )).alias("event_json")
)

display(orders_events.limit(5))
```

### Cell 2 — Create temp views (for SQL parts)

```python
customers.createOrReplaceTempView("v_customers")
orders_events.createOrReplaceTempView("v_orders_events")
```

---

# Tasks (choose the order; aim for 20–30 minutes total)

## Task 1 — Parse nested JSON and flatten to columns
**Goal:** Turn `event_json` into columns: `event_type`, `event_ts`, `channel`, `campaign`.

**What I’m looking for**
- Correct schema definition for `from_json`
- Clean column selection

**Expected approach (hint)**
```python
from pyspark.sql.types import StructType, StructField, StringType, TimestampType

schema = StructType([
    StructField("event_type", StringType()),
    StructField("event_ts", TimestampType()),
    StructField("metadata", StructType([
        StructField("channel", StringType()),
        StructField("campaign", StringType())
    ]))
])

parsed = (orders_events
    .withColumn("event", F.from_json("event_json", schema))
    .select(
        "order_id","customer_id","order_ts","amount","status","updated_at",
        F.col("event.event_type").alias("event_type"),
        F.col("event.event_ts").alias("event_ts"),
        F.col("event.metadata.channel").alias("channel"),
        F.col("event.metadata.campaign").alias("campaign"),
    )
)
```

---

## Task 2 — Deduplicate orders to the latest version
**Goal:** Keep only the latest row per `order_id` by `updated_at` (tie-breaker: highest `status` lexicographically is fine).

**What I’m looking for**
- Window + row_number (or aggregate+join) and correct filtering.

**Expected solution pattern**
```python
w = W.partitionBy("order_id").orderBy(F.col("updated_at").desc(), F.col("status").desc())
dedup = parsed.withColumn("rn", F.row_number().over(w)).filter("rn=1").drop("rn")
```

---

## Task 3 — Build a Silver Delta table (partitioned)
**Goal:** Write `dedup` as Delta, partitioned by `order_date` derived from `order_ts`.

**What I’m looking for**
- Deriving `order_date`, choosing partition, correct write mode
- Awareness of small files (optional mention)

**Example**
```python
silver = dedup.withColumn("order_date", F.to_date("order_ts"))

silver_path = "/tmp/interview/silver_orders_delta"
(silver.write.format("delta")
    .mode("overwrite")
    .partitionBy("order_date")
    .save(silver_path)
)

spark.read.format("delta").load(silver_path).createOrReplaceTempView("silver_orders")
```

---

## Task 4 — Create a Gold aggregate: daily revenue + top segment
**Goal:** For each `order_date`, compute total revenue and the segment with the highest revenue.

**What I’m looking for**
- Correct join to customers
- GroupBy + window ranking

**Expected approach**
```python
joined = (spark.table("silver_orders")
          .join(customers, "customer_id", "left"))

daily_segment = (joined
    .groupBy("order_date", "segment")
    .agg(F.sum("amount").alias("revenue"))
)

w2 = W.partitionBy("order_date").orderBy(F.col("revenue").desc())
gold = (daily_segment
    .withColumn("rn", F.row_number().over(w2))
    .groupBy("order_date")
    .agg(
        F.sum("revenue").alias("total_revenue"),  # note: sum over segments == total
        F.max(F.when(F.col("rn")==1, F.col("segment"))).alias("top_segment")
    )
)

display(gold.orderBy(F.desc("order_date")).limit(10))
```

---

## Task 5 — Upsert (MERGE) incremental updates into the Silver table
**Scenario:** You receive a new batch `new_orders` containing updates for existing `order_id`s and some new ones.  
**Goal:** MERGE into the existing Delta table on `order_id`, keeping latest `updated_at`.

### Provide the candidate a “new batch” (PySpark)
```python
new_orders = orders_events.sample(False, 0.02, seed=42) \
    .withColumn("amount", F.col("amount") + F.round(F.rand()*10, 2)) \
    .withColumn("updated_at", F.expr("timestampadd(minute, 90, updated_at)"))

# Parse and dedup new batch the same way
new_parsed = (new_orders
    .withColumn("event", F.from_json("event_json", schema))
    .select(
        "order_id","customer_id","order_ts","amount","status","updated_at",
        F.col("event.event_type").alias("event_type"),
        F.col("event.event_ts").alias("event_ts"),
        F.col("event.metadata.channel").alias("channel"),
        F.col("event.metadata.campaign").alias("campaign"),
    )
)

w = W.partitionBy("order_id").orderBy(F.col("updated_at").desc(), F.col("status").desc())
new_dedup = new_parsed.withColumn("rn", F.row_number().over(w)).filter("rn=1").drop("rn") \
    .withColumn("order_date", F.to_date("order_ts"))

new_dedup.createOrReplaceTempView("new_dedup")
```

### Candidate task: MERGE using SQL
**What I’m looking for**
- MERGE statement correctness
- Handling “latest wins” logic (only update when source is newer)

**Expected MERGE pattern**
```sql
MERGE INTO delta.`/tmp/interview/silver_orders_delta` AS t
USING new_dedup AS s
ON t.order_id = s.order_id
WHEN MATCHED AND s.updated_at > t.updated_at THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
;
```

---

## Task 6 — SQL challenge: Top 10 customers by 30‑day revenue
**Goal:** Use SQL (preferred) to return top 10 customers by revenue in last 30 days, plus their country and segment.

**Expected techniques**
- Filter by date
- Join dimension
- Group by and order

**Example solution**
```sql
SELECT
  o.customer_id,
  c.country,
  c.segment,
  SUM(o.amount) AS revenue_30d
FROM silver_orders o
LEFT JOIN v_customers c
  ON o.customer_id = c.customer_id
WHERE o.order_ts >= dateadd(day, -30, current_timestamp())
GROUP BY o.customer_id, c.country, c.segment
ORDER BY revenue_30d DESC
LIMIT 10;
```

---

# Performance mini‑discussion (2 minutes)

Ask the candidate:
1) Show `EXPLAIN` for the SQL in Task 6 and explain where the cost is.  
2) One improvement they’d try (examples: broadcast `customers`, filter early, reduce columns, ensure partition pruning, optimize small files, ZORDER if needed).

**Good answers include**
- Identifies shuffle in aggregation or join
- Mentions broadcast join for small dim
- Mentions partition pruning by `order_date` and ensuring predicates hit partition column
- Mentions OPTIMIZE to reduce small files

---

## Evaluation guide (quick)

- **Pass (strong)**: completes Tasks 1–3 + either 4 or 6, and can explain merge + perf trade‑offs.
- **Pass (ok)**: correct dedup + basic write + basic SQL aggregate; merge partially correct.
- **Concern**: can’t dedup reliably, incorrect joins/windows, or doesn’t understand Delta MERGE semantics.

---

## Optional extensions (if they finish early)
- Add a quarantine table for bad records (null customer_id, negative amount)
- Add a watermark for incremental processing (only process last N days)
- Demonstrate CDF consumption from the Silver table

