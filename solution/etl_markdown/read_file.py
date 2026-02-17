# db_utils.py
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

def setup_database() -> Engine:
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        raise RuntimeError("DATABASE_URL is missing. Set it to your sqlite file path.")

    # Fail fast for sqlite files (prevents auto-creating appdb)
    if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:////"):
        # relative path -> resolve relative to this file's directory (project)
        rel = db_url.replace("sqlite:///", "", 1)
        abs_path = (Path(__file__).resolve().parent / rel).resolve()
        db_url = f"sqlite:///{abs_path}"

    if db_url.startswith("sqlite:////"):
        abs_path = Path(db_url.replace("sqlite:////", "/", 1))
        if not abs_path.exists():
            raise RuntimeError(f"SQLite DB file not found: {abs_path}")

    engine = create_engine(
        db_url,
        future=True,
        connect_args={"check_same_thread": False} if db_url.startswith("sqlite") else {},
    )
    print(f"✅ Using DB: {engine.url}")
    return engine
