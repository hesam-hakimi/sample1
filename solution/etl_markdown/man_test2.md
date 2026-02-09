Implement strict SQL safety checks.

Create:
- app/sql_safety.py with functions:
  1) is_read_only_select(sql: str) -> bool
     - Allow only SELECT or WITH ... SELECT
     - Reject if contains any of these (case-insensitive):
       INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, MERGE, EXEC, EXECUTE, GRANT, REVOKE, DENY, ;, --, /*, xp_
  2) validate_metadata_sql(sql: str) -> None
     - Must be read-only select
     - Must reference ONLY meta. schema tables (meta.Tables, meta.Columns, meta.Relationships, meta.BusinessTerms)
     - If violated, raise ValueError with reason
  3) validate_business_sql(sql: str) -> None
     - Must be read-only select
     - Must reference ONLY dbo. tables from our POC set:
       dbo.Customers, dbo.Accounts, dbo.Transactions, dbo.Merchants, dbo.Branches
     - If violated, raise ValueError with reason

Add tests:
- tests/test_sql_safety.py covering good and bad queries, including:
  - CTE allowed
  - semicolon rejected
  - comment rejected
  - metadata query referencing dbo rejected
  - business query referencing meta rejected
