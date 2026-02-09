Create SQL scripts for a Banking/Finance POC with BOTH:
(A) business tables (dbo schema) and (B) metadata tables (meta schema) that describe the business tables.

Create these files exactly:
- sql/01_create_banking_schema.sql
- sql/02_create_metadata_schema.sql
- sql/03_seed_sample_data.sql

Requirements:
- Scripts should be idempotent (safe to rerun). Use IF OBJECT_ID(...) IS NOT NULL DROP... patterns.
- Use SQL Server syntax.
- Keep business domain realistic: Customers, Accounts, Transactions, Merchants, Branches.
- Metadata must support:
  1) table definition + field definition
  2) field datatype + PK/FK
  3) entity relationships
  4) business definitions/glossary terms

Implement schemas:
Business tables in dbo:
- dbo.Customers(CustomerId PK, FirstName, LastName, DateOfBirth, Segment, CreatedAt)
- dbo.Branches(BranchId PK, BranchName, City, Province)
- dbo.Accounts(AccountId PK, CustomerId FK->Customers, BranchId FK->Branches, AccountType, OpenDate, Status, Currency, CurrentBalance)
- dbo.Merchants(MerchantId PK, MerchantName, MCC, Category)
- dbo.Transactions(TransactionId PK, AccountId FK->Accounts, MerchantId FK->Merchants NULL, TransactionDate, Amount, Direction, Channel, Description)

Metadata schema meta:
- meta.Tables(TableId PK, SchemaName, TableName, TableDescription, BusinessDomain)
- meta.Columns(ColumnId PK, TableId FK->meta.Tables, ColumnName, DataType, IsNullable, IsPrimaryKey, IsForeignKey, ReferencesTable, ReferencesColumn, ColumnDescription, BusinessDefinition)
- meta.Relationships(RelationshipId PK, FromSchema, FromTable, FromColumn, ToSchema, ToTable, ToColumn, Cardinality, RelationshipDescription)
- meta.BusinessTerms(TermId PK, Term, Definition, Synonyms, RelatedTables, RelatedColumns)

Seed data:
- Insert ~10 customers, 2-3 branches, ~12 accounts, ~8 merchants, ~80 transactions across accounts.
- Populate meta.* tables to fully describe dbo.* tables and relationships (including business definitions).

Add a short README comment at top of each SQL file explaining the purpose and run order.
