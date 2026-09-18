import atexit
from threading import Lock
from typing import ContextManager

import psycopg
from psycopg import Connection
from psycopg_pool import ConnectionPool

from src.core.config import Settings


class DatabaseConfigurationError(RuntimeError):
    """PostgreSQL 연결 설정이 없을 때 발생한다."""


_pool_lock = Lock()
_pool: ConnectionPool | None = None
_pool_key: tuple[str, int] | None = None


def close_database_pool() -> None:
    global _pool, _pool_key
    with _pool_lock:
        pool, _pool, _pool_key = _pool, None, None
    if pool is not None:
        pool.close()


atexit.register(close_database_pool)


def connect_database(settings: Settings) -> ContextManager[Connection]:
    """설정된 PostgreSQL 연결을 생성한다.

    Args:
        settings: DATABASE_URL과 연결 제한시간을 담은 애플리케이션 설정.

    Returns:
        context manager로 사용할 수 있는 psycopg Connection.

    Raises:
        DatabaseConfigurationError: DATABASE_URL이 설정되지 않았을 때.
        psycopg.Error: PostgreSQL 연결을 생성하지 못했을 때.
    """
    if not settings.database_configured:
        raise DatabaseConfigurationError(
            "Database is not configured. Set DATABASE_URL in LLM/.env or "
            "PostgreSQL fields in the root .env."
        )
    conninfo = (
        settings.database_url.get_secret_value().strip()
        if settings.database_url is not None else ""
    )
    if not conninfo or conninfo.upper().startswith("YOUR_"):
        conninfo = psycopg.conninfo.make_conninfo(
            host=settings.db_host,
            port=settings.db_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=(
                settings.postgres_password.get_secret_value()
                if settings.postgres_password is not None else ""
            ),
        )
    key = (conninfo, settings.database_connect_timeout)
    global _pool, _pool_key
    with _pool_lock:
        if _pool is None or _pool_key != key:
            if _pool is not None:
                _pool.close()
            _pool = ConnectionPool(
                conninfo,
                kwargs={"connect_timeout": settings.database_connect_timeout},
                min_size=1,
                max_size=16,
                check=ConnectionPool.check_connection,
                open=True,
            )
            _pool_key = key
        pool = _pool
    return pool.connection()
