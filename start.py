import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def ensure_venv() -> None:
    if Path(sys.prefix).resolve() == VENV_DIR.resolve():
        return
    if not VENV_PYTHON.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])
    raise SystemExit(
        subprocess.call([str(VENV_PYTHON), str(ROOT / "start.py"), *sys.argv[1:]])
    )


def ensure_deps() -> None:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")]
    )


def ensure_frontend() -> None:
    frontend = ROOT / "frontend"
    npm = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.check_call([npm, "install"], cwd=frontend)
    subprocess.check_call([npm, "run", "build"], cwd=frontend)


def wait_for_postgres(dsn: str, timeout: int = 60) -> None:
    import psycopg

    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise SystemExit(f"PostgreSQL did not become ready: {last_error}")


def main() -> None:
    load_env(ROOT / ".env")
    ensure_venv()
    ensure_deps()
    sys.path.insert(0, str(ROOT / "backend"))

    from app.bootstrap import admin_dsn, prepare_database
    from app.config import API_HOST, API_PORT, DATABASE_URL

    reset = "--reset" in sys.argv
    serve = "--no-serve" not in sys.argv

    subprocess.check_call(
        ["docker", "compose", "up", "-d", "postgres"],
        cwd=ROOT,
    )
    wait_for_postgres(admin_dsn(DATABASE_URL))
    prepare_database(DATABASE_URL, reset=reset)
    print(f"Demo database is ready at {DATABASE_URL}", flush=True)
    print("Alice (East): X-Actor-Token: east-alice", flush=True)
    print("Bob (West):   X-Actor-Token: west-bob", flush=True)
    if not serve:
        return

    ensure_frontend()
    import uvicorn

    print(f"API listening on http://{API_HOST}:{API_PORT}", flush=True)
    uvicorn.run(
        "app.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
