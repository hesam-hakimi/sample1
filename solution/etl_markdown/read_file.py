import csv
from pathlib import Path
import pandas as pd

EDC_FILE_PATH = Path(r".\source_data\Weekly-Inventory-of-Certified-Assets-MOAR-as-of-2025-10-05.csv")
OUTPUT_XLSX = Path(r".\output\Weekly-Inventory-FULL.xlsx")

CHUNK_SIZE = 200_000          # adjust (100k–500k typical)
MAX_ROWS_PER_SHEET = 1_000_000  # keep under Excel limit (1,048,576)

TEXT_COLS = ["BUSINESS_DESCRIPTION"]  # add more columns if needed


def flatten_newlines(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = df[c].astype(str).str.replace(r"[\r\n]+", " ", regex=True)
    return df


def main():
    OUTPUT_XLSX.parent.mkdir(parents=True, exist_ok=True)

    reader = pd.read_csv(
        EDC_FILE_PATH,
        sep="|",
        engine="python",
        quoting=csv.QUOTE_NONE,     # important for messy quotes
        dtype=str,
        keep_default_na=False,
        on_bad_lines="warn",
        chunksize=CHUNK_SIZE,       # ✅ stream in chunks
    )

    sheet_idx = 1
    rows_in_sheet = 0
    first_chunk_for_sheet = True

    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
        for chunk in reader:
            chunk = flatten_newlines(chunk, TEXT_COLS)

            # If current sheet is full, start a new one
            if rows_in_sheet + len(chunk) > MAX_ROWS_PER_SHEET:
                sheet_idx += 1
                rows_in_sheet = 0
                first_chunk_for_sheet = True

            sheet_name = f"Sheet{sheet_idx}"

            # Write chunk
            chunk.to_excel(
                writer,
                sheet_name=sheet_name,
                index=False,
                header=first_chunk_for_sheet,
                startrow=rows_in_sheet if not first_chunk_for_sheet else 0,
            )

            rows_in_sheet += len(chunk)
            first_chunk_for_sheet = False

            print(f"✅ Wrote {len(chunk):,} rows to {sheet_name} (total in sheet: {rows_in_sheet:,})")

    print(f"\n✅ Done. Output: {OUTPUT_XLSX}")


if __name__ == "__main__":
    main()
