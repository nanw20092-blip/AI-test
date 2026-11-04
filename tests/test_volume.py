import csv
import os
import subprocess
import sys
import tempfile
import threading
import time
from io import StringIO
from pathlib import Path

import httpx
import pytest

os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/audi_test"

from app.volume import VOLUME_COUNT, generate_volume

pytestmark = pytest.mark.volume

ROOT = Path(__file__).resolve().parents[1]
ALICE = {"X-Actor-Token": "east-alice"}


def test_hundred_thousand_export_is_stable_while_list_works(seeded):
    inserted = generate_volume(os.environ["DATABASE_URL"], VOLUME_COUNT)
    assert inserted == VOLUME_COUNT

    port = _free_port()
    log_path = Path(tempfile.gettempdir()) / "audi-volume-uvicorn.log"
    log = log_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend")
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT / "backend",
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_until_ready(base)
        params = {"q": "Target", "sort": "issued_date", "order": "asc"}
        first_body, elapsed = _export_while_listing(base, params)
        assert elapsed < 60
        started = time.perf_counter()
        second = httpx.get(
            f"{base}/api/certificates/export",
            headers=ALICE,
            params=params,
            timeout=60,
            trust_env=False,
        )
        assert time.perf_counter() - started < 60
        assert second.status_code == 200
        assert second.text == first_body

        rows = list(csv.DictReader(StringIO(first_body)))
        assert len(rows) == 1000
        assert [row["serial_number"] for row in rows] == [
            f"EAST-VOL-{index:08d}" for index in range(1000)
        ]
        assert len({row["issued_at_local"] for row in rows}) == 1
        assert rows[0]["learner_name"] == "Target Lee, Jr."

        west = httpx.get(
            f"{base}/api/certificates/export",
            headers={"X-Actor-Token": "west-bob"},
            params=params,
            timeout=30,
            trust_env=False,
        )
        assert list(csv.DictReader(StringIO(west.text))) == []
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        log.close()


def _export_while_listing(base: str, params: dict) -> tuple[str, float]:
    started = threading.Event()
    release = threading.Event()
    box: dict = {}

    def read_export() -> None:
        try:
            t0 = time.perf_counter()
            with httpx.stream(
                "GET",
                f"{base}/api/certificates/export",
                headers=ALICE,
                params=params,
                timeout=60,
                trust_env=False,
            ) as response:
                assert response.status_code == 200
                iterator = response.iter_bytes()
                first = next(iterator)
                box["first"] = first
                started.set()
                if not release.wait(timeout=20):
                    raise TimeoutError("list request did not finish during export")
                chunks = [first]
                for chunk in iterator:
                    chunks.append(chunk)
                box["body"] = b"".join(chunks).decode("utf-8")
                box["elapsed"] = time.perf_counter() - t0
        except Exception as exc:
            box["error"] = exc
            started.set()

    thread = threading.Thread(target=read_export)
    thread.start()
    assert started.wait(timeout=30)
    if "error" in box:
        raise box["error"]
    listed = httpx.get(
        f"{base}/api/certificates",
        headers=ALICE,
        params={"q": "Alex Lee", "page_size": 5},
        timeout=10,
        trust_env=False,
    )
    assert listed.status_code == 200
    assert any(item["serial_number"] == "EAST-SAFETY-ALEX" for item in listed.json()["items"])
    release.set()
    thread.join(timeout=60)
    if "error" in box:
        raise box["error"]
    assert not thread.is_alive()
    return box["body"], box["elapsed"]


def _wait_until_ready(base: str) -> None:
    deadline = time.perf_counter() + 60
    last_error = None
    while time.perf_counter() < deadline:
        try:
            response = httpx.get(f"{base}/api/health", timeout=2, trust_env=False)
            if response.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.2)
    log_path = Path(tempfile.gettempdir()) / "audi-volume-uvicorn.log"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    raise RuntimeError(f"API did not start: {last_error}\n{log_text}")


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
