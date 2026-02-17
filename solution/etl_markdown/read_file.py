# db_utils.py
from __future__ import annotations

import os
import re
from typing import Tuple, List, Dict, Any
import pandas as pd
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine


def setup_database() -> Engine:
    db_url = (os.getenv("DATABASE_URL") or "sqlite:///app.db").strip()
    return create_engine(db_url, future=True)


def get_table_schemas(engine: Engine) -> List[Dict[str, Any]]:
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


def normalize_sql_for_engine(sql: str, engine: Engine) -> str:
    """
    If SQLite: strip schema/database prefixes like schema.table -> table
    without touching quoted identifiers such as "schema"."table" or [schema].[table].
    """
    s = (sql or "").strip()
    dialect = getattr(engine.dialect, "name", "").lower()
    if dialect != "sqlite":
        return s

    # Replace abc.def -> def only when abc/def look like identifiers and are NOT quoted
    pattern = re.compile(r'(?<!["\[\]`])\b([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)\b')
    return pattern.sub(r"\2", s)


def _apply_preview_limit(sql: str, engine: Engine, max_rows: int) -> str:
    s = (sql or "").strip().rstrip(";")
    low = s.lower()

    if not (low.startswith("select") or low.startswith("with")):
        return s

    dialect = getattr(engine.dialect, "name", "").lower()

    if dialect in {"sqlite", "postgresql", "mysql"}:
        if " limit " in low:
            return s
        return f"{s} LIMIT {int(max_rows)}"

    if dialect in {"mssql"}:
        # If already TOP, do nothing
        if low.startswith("select") and " top " in low[:40]:
            return s
        import re as _re
        m = _re.match(r"^\s*select\s+(distinct\s+)?", s, flags=_re.I)
        if not m:
            return s
        distinct = (m.group(1) or "")
        rest = s[m.end():]
        return f"SELECT {distinct}TOP ({int(max_rows)}) {rest}"

    return s


def execute_sql_df(sql: str, engine: Engine, max_rows: int = 500) -> Tuple[pd.DataFrame, str]:
    # ✅ NEW: normalize SQL for SQLite so schema prefixes won't break
    sql = normalize_sql_for_engine(sql, engine)

    sql_limited = _apply_preview_limit(sql, engine, max_rows=max_rows)

    with engine.begin() as conn:
        low = sql_limited.strip().lower()
        if low.startswith("select") or low.startswith("with"):
            df = pd.read_sql_query(text(sql_limited), conn)
            status = f"✅ Returned {len(df)} rows (preview up to {max_rows})"
            return df, status

        res = conn.execute(text(sql_limited))
        return pd.DataFrame(), f"✅ Statement executed. Rows affected: {res.rowcount}"
