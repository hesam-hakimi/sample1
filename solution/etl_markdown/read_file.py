import csv
from pathlib import Path
import pandas as pd

SRC = Path(r".\source_data\Weekly-Inventory-of-Certified-Assets-MOAR-as-of-2025-10-05.csv")
CLEAN = Path(r".\output\Weekly-Inventory-cleaned.csv")
XLSX = Path(r".\output\Weekly-Inventory-FULL.xlsx")

CHUNK_SIZE = 200_000
MAX_ROWS_PER_SHEET = 1_000_000           # keep under Excel limit (1,048,576)
TEXT_COLS = ["BUSINESS_DESCRIPTION"]      # add more columns if needed


def repair_pipe_file(src: Path, dst: Path, encoding="utf-8") -> int:
    """
    Repairs files where a row is broken by unquoted newlines inside a field.
    Joins physical lines until delimiter count matches header delimiter count.
    Replaces the embedded newline with a space.
    Returns number of repaired rows written.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with open(src, "r", encoding=encoding, errors="replace", newline="") as f, \
         open(dst, "w", encoding=encoding, newline="") as out:

        header = f.readline()
        if not header:
            raise ValueError("Empty file")

        header = header.rstrip("\r\n")
        out.write(header + "\n")

        expected_pipes = header.count("|")

        buf = ""
        for line in f:
            line = line.rstrip("\r\n")

            # join broken rows: replace the physical newline with a space
            buf = (buf + " " + line) if buf else line

            # keep appending until we have enough separators for a complete row
            if buf.count("|") < expected_pipes:
                continue

            out.write(buf + "\n")
            written += 1
            buf = ""

        # write any leftover (rare)
        if buf.strip():
            out.write(buf + "\n")
            written += 1

    return written


def flatten_newlines(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    # after repair, this is mostly for nicer Excel display
    for c in cols:
        if c in df.columns:
            df[c] = df[c].astype(str).str.replace(r"[\r\n]+", " ", regex=True)
    return df


def main():
    # 1) Repair the raw file so rows don't split
    rows = repair_pipe_file(SRC, CLEAN)
    print(f"✅ Repaired + wrote cleaned CSV rows: {rows:,} -> {CLEAN}")

    # 2) Stream cleaned file into Excel (multi-sheet)
    reader = pd.read_csv(
        CLEAN,
        sep="|",
        engine="python",
        quoting=csv.QUOTE_NONE,     # treat " as normal char (messy quotes safe)
        dtype=str,
        keep_default_na=False,
        on_bad_lines="warn",
        chunksize=CHUNK_SIZE,
    )

    sheet_idx = 1
    rows_in_sheet = 0
    first_chunk_for_sheet = True

    XLSX.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(XLSX, engine="openpyxl") as writer:
        for chunk in reader:
            chunk = flatten_newlines(chunk, TEXT_COLS)

            if rows_in_sheet + len(chunk) > MAX_ROWS_PER_SHEET:
                sheet_idx += 1
                rows_in_sheet = 0
                first_chunk_for_sheet = True

            sheet_name = f"Sheet{sheet_idx}"

            chunk.to_excel(
                writer,
                sheet_name=sheet_name,
                index=False,
                header=first_chunk_for_sheet,
                startrow=0 if first_chunk_for_sheet else rows_in_sheet,
            )

            rows_in_sheet += len(chunk)
            first_chunk_for_sheet = False
            print(f"✅ Wrote {len(chunk):,} rows to {sheet_name} (sheet total: {rows_in_sheet:,})")

    print(f"\n✅ Done: {XLSX}")


if __name__ == "__main__":
    main()
