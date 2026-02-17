from __future__ import annotations

import os
from typing import Dict, List, Tuple

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"


def setup_database() -> Engine:
    """
    Example: sqlite database from env.
    """
    db_url = os.getenv("DATABASE_URL", "sqlite:///deposits_data2.db")
    return create_engine(db_url, future=True)


def get_table_schemas(engine: Engine) -> Dict[str, List[str]]:
    """
    Returns {table_name: [col1, col2, ...]} for validation and prompts.
    For sqlite: no schema.
    """
    dialect = getattr(engine.dialect, "name", "").lower()
    schemas: Dict[str, List[str]] = {}

    with engine.connect() as conn:
        if dialect == "sqlite":
            # tables/views
            rows = conn.execute(
                text(
                    "SELECT name, type FROM sqlite_master "
                    "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'"
                )
            ).fetchall()

            for name, _typ in rows:
                cols = conn.execute(text(f"PRAGMA table_info('{name}')")).fetchall()
                schemas[name] = [c[1] for c in cols]  # second column is name
            return schemas

        # generic fallback (best effort)
        # You can expand for other dialects later
        rows = conn.execute(text("SELECT 1")).fetchall()
        _ = rows
        return schemas


def apply_preview_limit(sql: str, engine: Engine, max_rows: int) -> str:
    s = (sql or "").strip().rstrip(";")
    if not s:
        return s
    low = s.lower()
    is_select = low.startswith("select") or low.startswith("with")
    if not is_select:
        return s

    dialect = getattr(engine.dialect, "name", "").lower()
    if dialect == "sqlite":
        if " limit " in low:
            return s
        return f"{s} LIMIT {max_rows}"

    if dialect in ("mssql", "sqlserver"):
        # naive TOP injection if no TOP
        if " top " in low[:80]:
            return s
        import re
        m = re.match(r"^\s*select\s+(distinct\s+)?", s, flags=re.I)
        if m:
            distinct = m.group(1) or ""
            rest = s[m.end():]
            return f"SELECT {distinct}TOP ({max_rows}) {rest}"
    return s


def execute_sql_df(sql: str, engine: Engine, max_rows: int = 500) -> Tuple[pd.DataFrame, str]:
    sql_limited = apply_preview_limit(sql, engine, max_rows=max_rows)

    with engine.begin() as conn:
        low = sql_limited.strip().lower()
        if low.startswith("select") or low.startswith("with"):
            df = pd.read_sql_query(text(sql_limited), conn)
            msg = f"✅ Returned {len(df)} rows (preview up to {max_rows})."
            return df, msg

        res = conn.execute(text(sql_limited))
        msg = f"✅ Statement executed. Rows affected: {res.rowcount}"
        return pd.DataFrame(), msg
