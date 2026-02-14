import json
import os
from pathlib import Path

import pandas as pd

EXCEL_PATH = os.getenv("RRDW_META_XLSX", "data/rrdw_meta_data.xlsx")
OUT_DIR = Path(os.getenv("OUT_DIR", "out"))
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Your "field" sheet order MUST start exactly like this (extra columns allowed AFTER these)
FIELD_BASE_COLUMNS_ORDERED = [
    "MAL_CODE",
    "SCHEMA_NAME",
    "TABLE_NAME",
    "COLUMN_NAME",
    "SECURITY_CLASSIFICATION_CANDIDATE",
    "PII",
    "PCI",
    "BUSINESS_NAME",
    "BUSINESS_DESCRIPTION",
    "DATA_TYPE",
]

TABLE_REQUIRED = ["SCHEMA_NAME", "TABLE_NAME", "TABLE_BUSINESS_NAME", "TABLE_BUSINESS_DESCRIPTION"]
REL_REQUIRED = ["FROM_SCHEMA", "FROM_TABLE", "TO_SCHEMA", "TO_TABLE", "JOIN_TYPE", "JOIN_KEYS"]

def norm_colname(c: str) -> str:
    return str(c).strip().upper()

def norm_yesno(v) -> bool:
    s = str(v).strip().lower()
    return s in {"yes", "y", "true", "1", "t"}

def read_sheet(xlsx: str, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(xlsx, sheet_name=sheet, dtype=str)
    df.columns = [norm_colname(c) for c in df.columns]
    return df.fillna("")

def require_cols(df: pd.DataFrame, required: list[str], sheet: str):
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"[{sheet}] Missing required columns: {missing}")

def validate_field_order(df: pd.DataFrame):
    first_cols = list(df.columns[: len(FIELD_BASE_COLUMNS_ORDERED)])
    if first_cols != FIELD_BASE_COLUMNS_ORDERED:
        raise ValueError(
            "[field] Column order mismatch.\n"
            f"Expected first {len(FIELD_BASE_COLUMNS_ORDERED)} columns:\n"
            f"{FIELD_BASE_COLUMNS_ORDERED}\n"
            f"But got:\n{first_cols}\n"
            "You can add new columns only AFTER these."
        )

def stable_id(*parts: str) -> str:
    return ".".join([p.strip() for p in parts if p.strip()])

def build_field_docs(df: pd.DataFrame) -> list[dict]:
    docs = []
    for _, r in df.iterrows():
        schema = r["SCHEMA_NAME"].strip()
        table = r["TABLE_NAME"].strip()
        col = r["COLUMN_NAME"].strip()
        if not (schema and table and col):
            continue

        pii = norm_yesno(r.get("PII", ""))
        pci = norm_yesno(r.get("PCI", ""))

        doc = {
            "id": stable_id("field", schema, table, col),
            "mal_code": r.get("MAL_CODE", "").strip(),
            "schema_name": schema,
            "table_name": table,
            "column_name": col,
            "security_classification_candidate": r.get("SECURITY_CLASSIFICATION_CANDIDATE", "").strip(),
            "pii": pii,
            "pci": pci,
            "business_name": r.get("BUSINESS_NAME", "").strip(),
            "business_description": r.get("BUSINESS_DESCRIPTION", "").strip(),
            "data_type": r.get("DATA_TYPE", "").strip(),
            # Optional appended columns (only if you added them)
            "is_key": norm_yesno(r.get("IS_KEY", "")) if "IS_KEY" in df.columns else False,
            "is_filter_hint": norm_yesno(r.get("IS_FILTER_HINT", "")) if "IS_FILTER_HINT" in df.columns else False,
            "allowed_values": r.get("ALLOWED_VALUES", "").strip() if "ALLOWED_VALUES" in df.columns else "",
            "notes": r.get("NOTES", "").strip() if "NOTES" in df.columns else "",
        }

        # Searchable content string (for BM25/semantic + later embeddings)
        doc["content"] = (
            f"Schema: {schema}\n"
            f"Table: {table}\n"
            f"Column: {col}\n"
            f"Business Name: {doc['business_name']}\n"
            f"Description: {doc['business_description']}\n"
            f"Data Type: {doc['data_type']}\n"
            f"PII: {doc['pii']} PCI: {doc['pci']}\n"
            f"Security: {doc['security_classification_candidate']}\n"
            f"Allowed Values: {doc['allowed_values']}\n"
            f"Notes: {doc['notes']}\n"
        )
        docs.append(doc)
    return docs

def build_table_docs(df: pd.DataFrame) -> list[dict]:
    docs = []
    for _, r in df.iterrows():
        schema = r["SCHEMA_NAME"].strip()
        table = r["TABLE_NAME"].strip()
        if not (schema and table):
            continue

        doc = {
            "id": stable_id("table", schema, table),
            "schema_name": schema,
            "table_name": table,
            "table_business_name": r.get("TABLE_BUSINESS_NAME", "").strip(),
            "table_business_description": r.get("TABLE_BUSINESS_DESCRIPTION", "").strip(),
            "grain": r.get("GRAIN", "").strip(),
            "primary_keys": r.get("PRIMARY_KEYS", "").strip(),
            "default_filters": r.get("DEFAULT_FILTERS", "").strip(),
            "notes": r.get("NOTES", "").strip(),
        }
        doc["content"] = (
            f"Schema: {schema}\n"
            f"Table: {table}\n"
            f"Business Name: {doc['table_business_name']}\n"
            f"Description: {doc['table_business_description']}\n"
            f"Grain: {doc['grain']}\n"
            f"Primary Keys: {doc['primary_keys']}\n"
            f"Default Filters: {doc['default_filters']}\n"
            f"Notes: {doc['notes']}\n"
        )
        docs.append(doc)
    return docs

def build_rel_docs(df: pd.DataFrame) -> list[dict]:
    docs = []
    for _, r in df.iterrows():
        fs = r["FROM_SCHEMA"].strip()
        ft = r["FROM_TABLE"].strip()
        ts = r["TO_SCHEMA"].strip()
        tt = r["TO_TABLE"].strip()
        if not (fs and ft and ts and tt):
            continue

        doc = {
            "id": stable_id("rel", fs, ft, "to", ts, tt),
            "from_schema": fs,
            "from_table": ft,
            "to_schema": ts,
            "to_table": tt,
            "join_type": r.get("JOIN_TYPE", "").strip().upper(),
            "join_keys": r.get("JOIN_KEYS", "").strip(),
            "cardinality": r.get("CARDINALITY", "").strip(),
            "relationship_description": r.get("RELATIONSHIP_DESCRIPTION", "").strip(),
            "active": norm_yesno(r.get("ACTIVE", "Yes")),
        }
        doc["content"] = (
            f"FROM {fs}.{ft}\n"
            f"TO {ts}.{tt}\n"
            f"JOIN_TYPE: {doc['join_type']}\n"
            f"JOIN_KEYS: {doc['join_keys']}\n"
            f"CARDINALITY: {doc['cardinality']}\n"
            f"DESCRIPTION: {doc['relationship_description']}\n"
        )
        docs.append(doc)
    return docs

def write_jsonl(path: Path, docs: list[dict]):
    with path.open("w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

def main():
    if not Path(EXCEL_PATH).exists():
        raise FileNotFoundError(f"Excel not found: {EXCEL_PATH}")

    field_df = read_sheet(EXCEL_PATH, "field")
    validate_field_order(field_df)
    require_cols(field_df, FIELD_BASE_COLUMNS_ORDERED, "field")

    table_df = read_sheet(EXCEL_PATH, "table")
    require_cols(table_df, TABLE_REQUIRED, "table")

    rel_df = read_sheet(EXCEL_PATH, "relationship")
    require_cols(rel_df, REL_REQUIRED, "relationship")

    field_docs = build_field_docs(field_df)
    table_docs = build_table_docs(table_df)
    rel_docs = build_rel_docs(rel_df)

    write_jsonl(OUT_DIR / "field_docs.jsonl", field_docs)
    write_jsonl(OUT_DIR / "table_docs.jsonl", table_docs)
    write_jsonl(OUT_DIR / "relationship_docs.jsonl", rel_docs)

    print("✅ Build complete")
    print(f"- field docs: {len(field_docs)} -> {OUT_DIR/'field_docs.jsonl'}")
    print(f"- table docs: {len(table_docs)} -> {OUT_DIR/'table_docs.jsonl'}")
    print(f"- rel docs:   {len(rel_docs)} -> {OUT_DIR/'relationship_docs.jsonl'}")
    if field_docs:
        print("\nSample field doc id:", field_docs[0]["id"])
    if table_docs:
        print("Sample table doc id:", table_docs[0]["id"])
    if rel_docs:
        print("Sample rel doc id:", rel_docs[0]["id"])

if __name__ == "__main__":
    main()
