def get_db_dialect() -> str:
    """
    Parametric dialect hint for the LLM.
    If not set, default to sqlite (your current setup).
    """
    return (os.getenv("DB_DIALECT") or "sqlite").strip().lower()
