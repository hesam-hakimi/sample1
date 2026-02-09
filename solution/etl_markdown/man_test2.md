Implement a SQL Server access layer using pyodbc with Managed Identity authentication.

Create:
- app/db.py with:
  - create_connection() using connection string:
    Driver={SQL_DRIVER};Server=SQL_SERVER;Database=SQL_DATABASE;Encrypt=yes;TrustServerCertificate=no;Authentication=ActiveDirectoryMsi;
  - execute_query(sql: str, params: tuple | None = None, max_rows: int = 500) -> pandas.DataFrame
  - IMPORTANT: set a query timeout; limit rows to max_rows defensively
  - log key events but never log secrets

Create tests:
- tests/test_db.py:
  - Use unittest.mock / MagicMock to mock pyodbc.connect and cursor behavior
  - Test execute_query returns a DataFrame with expected columns/rows
  - Test max_rows is enforced
  - Test timeout is set on cursor

Constraints:
- Do not require a real SQL Server to run tests.
- Keep functions typed and small.
