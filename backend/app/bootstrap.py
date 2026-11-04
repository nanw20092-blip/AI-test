from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql

from app.config import DATABASE_URL
from app.seed import insert_seed, seed_if_empty

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

DROP_TABLES = """
DROP TABLE IF EXISTS
    idempotency_keys,
    audit_events,
    certificates,
    enrollments,
    learners,
    courses,
    admins,
    tenants,
    app_meta
CASCADE
"""

TRUNCATE_TABLES = """
TRUNCATE TABLE
    idempotency_keys,
    audit_events,
    certificates,
    enrollments,
    learners,
    courses,
    admins,
    tenants,
    app_meta
RESTART IDENTITY CASCADE
"""


def split_sql(script: str) -> list[str]:
    lines = []
    for line in script.splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(line)
    return [part.strip() for part in "\n".join(lines).split(";") if part.strip()]


def database_name(dsn: str) -> str:
    return urlsplit(dsn).path.lstrip("/")


def admin_dsn(dsn: str) -> str:
    parts = urlsplit(dsn)
    return urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment))


def ensure_database(dsn: str = DATABASE_URL) -> None:
    name = database_name(dsn)
    with psycopg.connect(admin_dsn(dsn), autocommit=True, connect_timeout=5) as conn:
        row = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (name,),
        ).fetchone()
        if row:
            return
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def apply_schema(conn) -> None:
    for statement in split_sql(SCHEMA_PATH.read_text(encoding="utf-8")):
        conn.execute(statement)


def reset_database(conn) -> None:
    conn.execute(DROP_TABLES)
    apply_schema(conn)
    insert_seed(conn)
    conn.execute("INSERT INTO app_meta (key, value) VALUES ('seed_version', '1')")


def truncate_and_seed(conn) -> None:
    conn.execute(TRUNCATE_TABLES)
    insert_seed(conn)
    conn.execute("INSERT INTO app_meta (key, value) VALUES ('seed_version', '1')")


def prepare_database(dsn: str = DATABASE_URL, *, reset: bool = False) -> None:
    ensure_database(dsn)
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            if reset:
                reset_database(conn)
            else:
                apply_schema(conn)
                seed_if_empty(conn)
