# Blockers & Mitigations

| Blocker ID | Blocker | Impact | Root Cause | Workaround (Tactical) | Fix (Strategic) | Owner | Status |
|---|---|---|---|---|---|---|---|
| B1 | Azure AI Search index count maxed (50) | Cannot create new indexes; limits scaling | Service quota / current design | Consolidate: fewer indexes, reuse fields, multi-tenant index strategy | Request quota increase / redesign indexing strategy | TBD | 🔴 |
| B2 | SQL user cannot create objects | Cannot create tables/views/staging needed | Missing privileges/role | Use existing schema only; use temp tables if allowed; use file extracts | Request permissions / new schema / DBA-managed objects | TBD | 🔴 |
| B3 | No Synapse/SRZ access from DevSandbox | Blocks “real dev data” route | Network/identity/access approvals | Copy subset data; use files; demo with smaller dataset | Approve connectivity path + firewall + creds | TBD | 🟡 |
| B4 | Collibra/Data Compass not ready | Limits metadata-driven automation | Tool readiness | Manual schema prompt pack | Integrate Collibra/Data Compass when ready | TBD | 🟡 |
