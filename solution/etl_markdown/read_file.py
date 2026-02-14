from pathlib import Path
import pandas as pd

# -------- Config --------
SRC = Path(r".\source_data\Weekly-Inventory-of-Certified-Assets-MOAR-as-of-2025-10-05.csv")
OUT_XLSX = Path(r".\output\Filtered_Tables.xlsx")

# These are SUBSTRINGS to match (e.g., "x" matches "x_base", "x_vw")
TARGET_TABLE_PATTERNS = {
    "x",
    "dac_edc",
    # add more...
}

CASE_INSENSITIVE = True
ONE_SHEET_PER_TABLE = True

# Excel limits
MAX_ROWS_PER_SHEET = 1_000_000  # keep under 1,048,576


def matches_any_pattern(table_name: str, patterns: set[str], case_insensitive: bool = True) -> bool:
    if table_name is None:
        return False
    if case_insensitive:
        tn = table_name.lower()
        pats = [p.lower() for p in patterns]
    else:
        tn = table_name
        pats = list(patterns)

    return any(p in tn for p in pats)


def stream_filter_tables_contains(src: Path, patterns: set[str], case_insensitive: bool):
    """
    Streams a pipe-delimited file and repairs rows broken by unquoted newlines.
    Yields (table_name, row_values_list) for rows where TABLE_NAME contains any pattern.
    """
    with open(src, "r", encoding="utf-8", errors="replace", newline="") as f:
        header_line = f.readline().rstrip("\r\n")
        headers = header_line.split("|")
        expected_cols = len(headers)

        if "TABLE_NAME" not in headers:
            raise ValueError('Column "TABLE_NAME" not found in file')

        table_idx = headers.index("TABLE_NAME")

        buffer = ""
        for line in f:
            line = line.rstrip("\r\n")

            # Join broken lines: newline inside a field becomes a space
            buffer = (buffer + " " + line) if buffer else line

            # Wait until the row looks complete (has enough separators)
            if buffer.count("|") < expected_cols - 1:
                continue

            # Split into exactly expected columns
            parts = buffer.split("|", maxsplit=expected_cols - 1)

            if len(parts) == expected_cols:
                tname = parts[table_idx]
                if matches_any_pattern(tname, patterns, case_insensitive):
                    yield tname, parts

            buffer = ""


def sanitize_sheet_name(name: str) -> str:
    """
    Excel sheet rules: max 31 chars; cannot contain: : \ / ? * [ ]
    """
    bad = [":", "\\", "/", "?", "*", "[", "]"]
    for ch in bad:
        name = name.replace(ch, "_")
    name = name.strip()
    return (name[:31] if len(name) > 31 else name) or "Sheet"


def main():
    # Read header once
    with open(SRC, "r", encoding="utf-8", errors="replace") as f:
        header_line = f.readline().rstrip("\r\n")
    headers = header_line.split("|")

    # Collect rows by actual TABLE_NAME found in file
    buckets: dict[str, list[list[str]]] = {}

    for tname, row in stream_filter_tables_contains(SRC, TARGET_TABLE_PATTERNS, CASE_INSENSITIVE):
        buckets.setdefault(tname, []).append(row)

    if not buckets:
        print(f"❌ No rows found where TABLE_NAME contains any of: {sorted(TARGET_TABLE_PATTERNS)}")
        return

    OUT_XLSX.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        if ONE_SHEET_PER_TABLE:
            for tname, rows in sorted(buckets.items(), key=lambda x: x[0].lower()):
                df = pd.DataFrame(rows, columns=headers)

                # Clean any leftover CR/LF chars in cells for nicer Excel display
                df = df.replace({"\r": " ", "\n": " "}, regex=True)

                sheet_base = sanitize_sheet_name(tname)

                # Split large tables across multiple sheets if needed
                if len(df) <= MAX_ROWS_PER_SHEET:
                    df.to_excel(writer, sheet_name=sheet_base, index=False)
                else:
                    part = 1
                    for start in range(0, len(df), MAX_ROWS_PER_SHEET):
                        chunk = df.iloc[start:start + MAX_ROWS_PER_SHEET]
                        sheet = sanitize_sheet_name(f"{sheet_base}_{part}")
                        chunk.to_excel(writer, sheet_name=sheet, index=False)
                        part += 1
        else:
            # Single combined sheet with all matched rows
            all_rows = []
            for _, rows in buckets.items():
                all_rows.extend(rows)

            df = pd.DataFrame(all_rows, columns=headers)
            df = df.replace({"\r": " ", "\n": " "}, regex=True)

            if len(df) <= MAX_ROWS_PER_SHEET:
                df.to_excel(writer, sheet_name="Filtered", index=False)
            else:
                part = 1
                for start in range(0, len(df), MAX_ROWS_PER_SHEET):
                    chunk = df.iloc[start:start + MAX_ROWS_PER_SHEET]
                    chunk.to_excel(writer, sheet_name=f"Filtered_{part}", index=False)
                    part += 1

    print("✅ Done")
    print(f"✅ Output: {OUT_XLSX}")
    print("✅ Matched table names:")
    for tname in sorted(buckets.keys(), key=str.lower):
        print(f"  - {tname}: {len(buckets[tname]):,} rows")


if __name__ == "__main__":
    main()
