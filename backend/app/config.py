import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/audi",
)
API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", "8088"))
