"""DB bootstrap. Postgres row queries first, SQLite fallback. No dump/TRUNCATE."""

from core.db import db_path, init_db


def persist() -> None:
    """Kept for call-site compatibility. Writes now go through core.repo."""
    return
