# Databricks Copilot Tools — One‑Page Feature List (Tech Lead)

> VS Code extension that exposes Databricks operations as **(1) GitHub Copilot Agent tools** and **(2) a structured sidebar UI** for faster development, debugging, testing, and performance tuning.

---

## Core Capabilities

### Connection & Identity
- Connect to Databricks workspaces via **PAT** or **Azure CLI OAuth**
- Workspace host + auth mode switching, credential management
- Select and persist **Default Cluster** (auto-start if stopped)
- Configure **Workspace Upload Folder** (where code/notebooks are uploaded before runs)

### Copilot Agent Tooling
- Each capability is available as a **Copilot LM tool** (tool schema + handler) and mirrored in the sidebar UI
- Tool outputs are **LLM-friendly**: structured JSON + Markdown summaries
- Designed for “ask → tool call → return results → propose fix” workflows

### SQL & Python Quick Execution (All‑Purpose Cluster)
- Execute SQL quickly on the default all‑purpose cluster (commands API)
- Execute Python snippets quickly on the default all‑purpose cluster
- Result rendering (tables, row limits, truncation notes) + retry on context issues

### Jobs & Runs
- Create ad-hoc runs from uploaded code (Python / notebooks)
- Create jobs from code and **run now**
- **Update existing jobs** (reuse jobId instead of creating new jobs) *(if enabled in your roadmap)*
- List recent runs, fetch run details (state, duration breakdown, run links)
- Fetch run output / errors when available (get-output), with clear messages for workspace restrictions

### Notebooks & Source Retrieval
- Fetch notebook source via workspace export (`format=SOURCE`) by:
  - direct workspace path, or
  - resolving from `jobId + taskKey`
- Optional truncation controls for large notebooks
- Upload local notebook/script to workspace (e.g., `/Shared/...`) *(if enabled in your roadmap)*

### Clusters
- List clusters and statuses (RUNNING/TERMINATED)
- Start cluster
- Get **cluster definition** (advanced settings, spark conf, tags, policies, runtime, etc.)
- Show “current cluster status” (best-effort; subject to API availability)

---

## Performance & Diagnostics

### Run Performance Analysis
- Analyze run duration (setup/execution/cleanup), task paths, cluster identity, run links
- Optional **Spark UI metrics** via driver‑proxy (when accessible):
  - Top stages by runtime / shuffle / spill
  - Executor summaries (skew, GC pressure, I/O hotspots)
- Graceful fallback when metrics cannot be fetched (403/404/timeout/no app match)

### Table Profiling
- Table layout: format (Delta), location, size, file count, partitioning
- Column stats: null %, approx distinct, min/max (best-effort; can degrade gracefully)

### SQL Explain
- Return execution plan to help diagnose shuffles, joins, scans, and partition pruning

---

## Developer Experience

### Sidebar Organization
- Categorized tree view: **Connection / Tools / Performance / Debug**
- Commands and actions surfaced as tree nodes and context menus
- Output shown via Markdown preview / output channel

### Quality & Release Workflow
- After changes:
  - `npm run compile`
  - `npm test`
  - `npm audit --audit-level=high`
- If all pass:
  - `npm version patch`
  - `npx vsce package` (produces a new VSIX)

### Security Posture
- Reuses Databricks auth flows (PAT/OAuth); no secret logging
- Operates under the user’s Databricks permissions (RBAC respected)
- Dependency scanning via `npm audit` in the standard workflow

---

## What It Can’t Do (Current/Typical Limits)
- Guaranteed live CPU/memory utilization for clusters (often not available via public APIs; may require external monitoring)
- Guaranteed Spark stage/executor metrics for every run (driver-proxy may be blocked; appId may not be resolvable)
- Guaranteed run output retrieval for multi-task job runs (workspace policies may restrict `get-output`)
- Replace Databricks admin controls or bypass workspace permissions

---

## Visual Placeholders (optional)
- 🧩 Architecture diagram: VS Code ⇄ Extension ⇄ Databricks REST APIs ⇄ Spark/Jobs/Clusters
- 🏷️ Badges: “Copilot Tools”, “Databricks Jobs”, “Spark Metrics”, “Delta Profiling”
