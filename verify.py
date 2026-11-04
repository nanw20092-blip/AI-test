import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"


def ensure_venv() -> None:
    if Path(sys.prefix).resolve() == VENV_DIR.resolve():
        return
    if not VENV_PYTHON.exists():
        raise SystemExit("Run python start.py before python verify.py.")
    raise SystemExit(subprocess.call([str(VENV_PYTHON), str(ROOT / "verify.py"), *sys.argv[1:]]))


def wait_for_postgres() -> None:
    import psycopg

    subprocess.check_call(["docker", "compose", "up", "-d", "postgres"], cwd=ROOT)
    dsn = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/audi",
    )
    admin = dsn.rsplit("/", 1)[0] + "/postgres"
    deadline = time.time() + 60
    last_error = None
    while time.time() < deadline:
        try:
            with psycopg.connect(admin, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise SystemExit(f"PostgreSQL did not become ready: {last_error}")


def main() -> None:
    ensure_venv()
    wait_for_postgres()
    marker = "volume" if "--volume" in sys.argv else "not volume"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-o",
        "addopts=",
        "-m",
        marker,
    ]
    raise SystemExit(subprocess.call(command, cwd=ROOT))


if __name__ == "__main__":
    main()
