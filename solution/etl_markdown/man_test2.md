## Fix: SimpleField keyword-only arguments error

Error:
`SimpleField() takes 0 positional arguments but 2 positional arguments (and 2 keyword-only arguments) were given`

### What to change
In `scripts/search_upload_metadata.py`, update ALL field definitions to use ONLY keyword arguments.

### Required edits
1) Replace any `SimpleField("name", "Edm.String", ...)` with:
- `SimpleField(name="name", type=SearchFieldDataType.String, key=..., filterable=..., sortable=..., facetable=..., retrievable=True)`

2) Replace any `SearchField("content", "Edm.String", ...)` with:
- `SearchField(name="content", type=SearchFieldDataType.String, searchable=True, retrievable=True)`

3) Use these imports (ensure they exist):
- `from azure.search.documents.indexes.models import SearchIndex, SimpleField, SearchField, SearchFieldDataType`

4) Use `SearchFieldDataType.String` instead of `"Edm.String"`
5) Use `SearchFieldDataType.Boolean` instead of `"Edm.Boolean"`

### Minimal correct examples (must match this style)
- Key field:
  `SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True, retrievable=True)`

- Filterable string:
  `SimpleField(name="schema_name", type=SearchFieldDataType.String, filterable=True, retrievable=True)`

- Searchable text:
  `SearchField(name="content", type=SearchFieldDataType.String, searchable=True, retrievable=True)`

- Boolean:
  `SimpleField(name="pii", type=SearchFieldDataType.Boolean, filterable=True, retrievable=True)`

### After patch
Run:
- `python scripts/search_upload_metadata.py`

### Output needed
Paste the console output (or full stack trace if it fails).
