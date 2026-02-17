from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def _is_sqlite(url: str) -> bool:
    return url.strip().lower().startswith("sqlite:")


def _normalize_sqlite_url(db_url: str) -> str:
    # sqlite:///relative.db -> resolve relative to this file's folder (project-like)
    if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:////"):
        rel = db_url.replace("sqlite:///", "", 1)
        abs_path = (Path(__file__).resolve().parent / rel).resolve()
        return f"sqlite:///{abs_path}"
    return db_url


def setup_database() -> Engine:
    """
    Creates SQLAlchemy engine.
    IMPORTANT: For sqlite, we FAIL FAST if the DB file doesn't exist to prevent
    accidental creation of an empty DB (e.g., 'appdb.db' problem).
    """
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL is missing. Set it in .env")

    db_url = _normalize_sqlite_url(db_url)

    if _is_sqlite(db_url):
        # absolute path: sqlite:////abs/path.db
        if db_url.startswith("sqlite:////"):
            abs_path = Path(db_url.replace("sqlite:////", "/", 1))
            if not abs_path.exists():
                raise RuntimeError(
                    f"SQLite DB file not found: {abs_path}\n"
                    "Set DATABASE_URL to an existing absolute path to avoid creating a new empty DB."
                )

    engine = create_engine(
        db_url,
        future=True,
        connect_args={"check_same_thread": False} if _is_sqlite(db_url) else {},
    )

    print(f"✅ Using DB: {engine.url}")
    return engine


def get_table_schemas(engine: Engine) -> Dict[str, List[str]]:
    """
    Returns {table_name: [col1, col2, ...]} based on the connected DB.
    For sqlite, uses sqlite_master + PRAGMA table_info.
    """
    dialect = (engine.dialect.name or "").lower()
    tables: Dict[str, List[str]] = {}

    if dialect == "sqlite":
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")).fetchall()
            for (tname,) in rows:
                cols = conn.execute(text(f"PRAGMA table_info('{tname}')")).fetchall()
                # PRAGMA table_info: cid, name, type, notnull, dflt_value, pk
                tables[tname] = [c[1] for c in cols]
        return tables

    # Generic fallback: INFORMATION_SCHEMA for common engines
    with engine.connect() as conn:
        try:
            rows = conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns ORDER BY table_name, ordinal_position"
            )).fetchall()
            for t, c in rows:
                tables.setdefault(str(t), []).append(str(c))
        except Exception:
            # best effort: return empty
            pass
    return tables


def execute_sql_df(engine: Engine, sql: str, max_rows: int = 500) -> Tuple[pd.DataFrame, str]:
    """
    Executes SQL and returns (DataFrame, status_text). Adds a preview LIMIT/TOP when possible.
    """
    sql2 = (sql or "").strip().rstrip(";")
    if not sql2:
        return pd.DataFrame(), "⚠️ Empty SQL."

    dialect = (engine.dialect.name or "").lower()

    # Apply preview limit safely
    def _apply_preview_limit(s: str) -> str:
        low = s.lower().lstrip()
        if not (low.startswith("select") or low.startswith("with")):
            return s
        if dialect == "sqlite":
            if " limit " in low:
                return s
            return f"{s} LIMIT {int(max_rows)}"
        if dialect in ("mssql", "mssql+pymssql", "mssql+pyodbc"):
            # naive TOP insertion for SELECT ...
            if re.search(r"\btop\b", low):
                return s
            m = re.match(r"^\s*select\s+(distinct\s+)?", s, flags=re.I)
            if not m:
                return s
            distinct = m.group(1) or ""
            rest = s[m.end():]
            return f"SELECT {distinct}TOP ({int(max_rows)}) {rest}"
        return s

    import re
    sql_limited = _apply_preview_limit(sql2)

    with engine.begin() as conn:
        low = sql_limited.lower().lstrip()
        if low.startswith("select") or low.startswith("with"):
            df = pd.read_sql_query(text(sql_limited), conn)
            shown = min(len(df), int(max_rows))
            return df, f"✅ Returned {len(df)} rows (showing up to {shown})."
        res = conn.execute(text(sql_limited))
        return pd.DataFrame(), f"✅ Statement executed. Rows affected: {res.rowcount}"
