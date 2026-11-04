from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import DATABASE_URL

pool: ConnectionPool | None = None


def init_pool(dsn: str = DATABASE_URL) -> ConnectionPool:
    global pool
    if pool is not None:
        return pool
    pool = ConnectionPool(
        dsn,
        min_size=1,
        max_size=10,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    pool.wait(timeout=30)
    return pool


def get_pool() -> ConnectionPool:
    if pool is None:
        raise RuntimeError("database pool is not initialized")
    return pool


def close_pool() -> None:
    global pool
    if pool is not None:
        pool.close()
        pool = None
