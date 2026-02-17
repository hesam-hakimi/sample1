# db_utils.py
from __future__ import annotations

import os
from typing import Tuple, List, Dict, Any
import pandas as pd
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine


def setup_database() -> Engine:
    db_url = (os.getenv("DATABASE_URL") or "sqlite:///app.db").strip()
    return create_engine(db_url, future=True)


def get_table_schemas(engine: Engine) -> List[Dict[str, Any]]:
    """
    Returns a list of tables for the LLM guardrail:
    [{"schema": "...", "table": "..."}]
    """
    insp = inspect(engine)
    out: List[Dict[str, Any]] = []
    try:
        schemas = insp.get_schema_names()
    except Exception:
        schemas = [None]

    for sch in schemas:
        try:
            tables = insp.get_table_names(schema=sch) if sch else insp.get_table_names()
        except Exception:
            continue
        for t in tables:
            out.append({"schema": sch or "", "table": t})
    return out


def _apply_preview_limit(sql: str, engine: Engine, max_rows: int) -> str:
    s = (sql or "").strip().rstrip(";")
    low = s.lower()

    # Only apply to SELECT/CTE
    if not (low.startswith("select") or low.startswith("with")):
        return s

    dialect = getattr(engine.dialect, "name", "").lower()

    # SQLite / Postgres / MySQL / etc
    if dialect in {"sqlite", "postgresql", "mysql"}:
        if " limit " in low:
            return s
        return f"{s} LIMIT {int(max_rows)}"

    # MSSQL / Azure SQL
    if dialect in {"mssql"}:
        # If already TOP, do nothing
        if low.startswith("select") and " top " in low[:40]:
            return s
        # Inject TOP after SELECT (and after DISTINCT if present)
        import re
        m = re.match(r"^\s*select\s+(distinct\s+)?", s, flags=re.I)
        if not m:
            return s
        distinct = (m.group(1) or "")
        rest = s[m.end():]
        return f"SELECT {distinct}TOP ({int(max_rows)}) {rest}"

    return s


def execute_sql_df(sql: str, engine: Engine, max_rows: int = 500) -> Tuple[pd.DataFrame, str]:
    sql_limited = _apply_preview_limit(sql, engine, max_rows=max_rows)

    with engine.begin() as conn:
        low = sql_limited.strip().lower()
        if low.startswith("select") or low.startswith("with"):
            df = pd.read_sql_query(text(sql_limited), conn)
            status = f"✅ Returned {len(df)} rows (preview up to {max_rows})"
            return df, status

        res = conn.execute(text(sql_limited))
        return pd.DataFrame(), f"✅ Statement executed. Rows affected: {res.rowcount}"
