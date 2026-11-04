import os

os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/audi_test"

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import apply_schema, ensure_database, truncate_and_seed
from app.db import close_pool, get_pool, init_pool
from app.main import app


@pytest.fixture(scope="session")
def database():
    ensure_database()
    init_pool()
    with get_pool().connection() as conn:
        with conn.transaction():
            apply_schema(conn)
    yield
    close_pool()


@pytest.fixture
def seeded(database):
    with get_pool().connection() as conn:
        with conn.transaction():
            truncate_and_seed(conn)
    return database


@pytest.fixture
def client(seeded):
    with TestClient(app) as test_client:
        yield test_client
