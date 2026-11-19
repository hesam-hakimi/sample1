# Find why the planning baseline hash differs (read-only)

The validator reports `Planning baseline hash differs: register_semantics` although every count matches. Find out what departs from the reviewed package.

This task is read-only. Change no package file, validator, hash, git state or Jira record, and repair nothing. Put any helper script outside `feature/` and run Python with `-X utf8 -B`.

1. For each path under `files` below, hash the file's bytes with SHA-256 after converting CRLF to LF, and compare the first 12 hex characters. Report matching, differing and missing files.

2. Import the validator unmodified and load `feature/task/TASK_DELIVERY_REGISTER.json` with its `unique_object_pairs` hook. Compute `canonical_sha256` for every top-level value and for every record in `tasks` (by its `key`). Compare the first 12 hex characters with `register_top_level` and `register_tasks`, and list every differing, missing and extra name. Also report the `source_revision` and `register_semantics` values pinned in the validator; the reviewed validator pins `3feaddccd2d9...` and `39da44d2bf18...`.

3. For each part that differs, look for the cause:
   - fields that sibling records do not have;
   - values that mention `ASKTD-`, Jira, tracker or ledger data;
   - damaged characters: U+FFFD, `â€`, `Ã`, or `?` where a dash, arrow or section sign belongs;
   - the file's modified time compared with the other package files;
   - if the folder is tracked, `git status --short` and `git diff --stat` for it (read-only git commands only).

4. Tell me in a few lines which file departs from the reviewed pair, where, and the most likely cause.

Reviewed fingerprints:

```json
{
  "files": {
    "feature/task/TASK_DELIVERY_REGISTER.json": "9cf375d59ad3",
    "feature/validation/validate_workflow_traceability.py": "084406756a7d",
    "feature/validation/test_workflow_traceability.py": "c880b02c188b",
    "feature/PACKAGE_MANIFEST.json": "30bc515be51a",
    "feature/task/TASK_DELIVERY_DETAILS.md": "8415cc52d088",
    "feature/task/TASK_DELIVERY_REGISTER.md": "94ef0915ea4a",
    "feature/shared/ASKTD_PRODUCTION_WORKFLOW_DECISION_REVIEW.md": "975cad59171b",
    "feature/shared/ASKTD_PLAN_AND_LINEAGE_REFERENCE.md": "e08934ba89ff",
    "feature/shared/AskTD_Delivery_Plans_and_Dependencies.md": "4b123f0b62a3",
    "feature/shared/ASKTD_NEW_SESSION_PROMPT.md": "9b6ec17680ef",
    "feature/shared/ASKTD_SESSION_HANDOFF.md": "ab00def7fb51"
  },
  "register_top_level": {
    "schema_version": "a51162aeeb05", "revision": "be9ee1cca338", "date": "3af512824d0e",
    "source_documentation_commit": "5e2be654beb3", "authority": "c6679ea985d9", "implementation_authorized": "fcbcf165908d",
    "tracker_sync_authorized": "fcbcf165908d", "canonical_plan_count": "e629fa6598d7", "canonical_outputs": "45bbf5c111ca",
    "portfolio_dependencies": "3db482c1cfd7", "count_interpretation": "7fbfb0777a09", "scope_evidence": "ddbc1ae2e1cf",
    "tasks": "3b8da9a2e864", "decisions": "a2ed30e9447c", "q1_package_crosswalk": "562526651150",
    "release_dates": "74234e98afe7", "effort_estimates": "74234e98afe7", "output_accounting": "60ad1b629964",
    "product_audit_mapping": "e162967dc8c1", "source_review": "1b8954fb2917", "master_delta_mapping": "1561c95875cb",
    "reference_control_mapping": "4b1d30b3db44", "registry_requirement_mapping": "5207eb350048", "continuity_requirement_mapping": "e565c4e61069",
    "release_gate_mapping": "d3a029ca6621", "registry_native_inventory": "74c00e0de095", "additional_reference_review": "e3b44391eb3c",
    "canonical_portfolio_dependency_count": "b7a56873cd77", "portfolio_dependency_register": "022642118573", "review_feedback": "195b16932008",
    "deposit_recipe_migration": "3ad0354d43ec", "durable_workflow": "dcc6a6bbd62e", "production_workflow_review": "1397e530ca2c"
  },
  "register_tasks": {
    "Task 2": "ca219312746d", "FND-03": "8e6af3dbf0da", "Task 3": "6b40fbc8ecb8", "FND-02": "d67faac51716",
    "Task 1": "018eda47f1e6", "Connections": "11db30e7aa19", "R1-A": "3da3b441b7c8", "R1-B": "0b07193d17c8",
    "REL-01": "81c8af1a2125", "ACCESS-01": "1e8933671d0e", "R1-D": "3802a916c789", "R1-E": "1565aa970adc",
    "POLICY-01": "e82302103a8e", "METHOD-01": "43f22dc4cc27", "RUN-01": "856f04d18a84", "ROUTE-01": "b1262c80a6fd",
    "ANALYSIS-01": "b670879e2d80", "R1-H": "361474dfed6e", "MODEL-01": "f75e9b947a76", "METER-01": "913457a3a401",
    "OPS-01": "5740657636e6", "R1-K": "887a749f4ded", "R1-L": "8a47243bed29", "ADOPT-01": "ad2223a35149",
    "MIG-01": "3b7de712b4c5", "MIG-02": "4d686e55c572", "MIG-03": "35eda75b1832", "MIG-04": "540cb78e744c",
    "MIG-05": "f5c674349036", "MIG-06": "e76ebe7bfb17", "MIG-07": "153f106ebafa", "MIG-08": "7db4115e4df8",
    "CONN-01": "6cb51dae76f1", "CONN-02": "58bbf6a0cd6e", "CONN-03": "e880ddf8a99f", "CONN-04": "530aa1f47eb6",
    "CONN-05": "2b3f36d725d6", "SAVE-01": "9f4a01aae43a", "HISTORY-01": "d3c56fee7177", "PREF-01": "e755c9219990",
    "TEMPLATE-01": "520f00bf9313", "TEMPLATE-02": "8188d38fdc49", "SHOWBACK-01": "1031ab312ea6", "BUDGET-01": "1de70ea84218",
    "REUSE-01": "d86135da62ed", "SCHEDULE-01": "c310326582c7", "SCHEDULE-02": "8badc8498cb6", "SUGGEST-01": "728da4dc085a",
    "IMPROVE-01": "4e696453e768", "REPORT-01": "bc3ddd32cd6c", "EXPORT-01": "15ce2cd486d5", "EXPAND-01": "df18804af9e6",
    "EXPAND-02": "b15b9499e6bf"
  }
}
```
