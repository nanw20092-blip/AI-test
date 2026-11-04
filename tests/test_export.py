import csv
import os
from io import StringIO

os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/audi_test"

from app.volume import generate_volume

ALICE = {"X-Actor-Token": "east-alice"}
BOB = {"X-Actor-Token": "west-bob"}


def rows_of(response) -> list[dict]:
    assert response.status_code == 200
    return list(csv.DictReader(StringIO(response.text)))


def test_export_uses_tenant_local_time_and_search(client):
    alice = rows_of(client.get("/api/certificates/export", headers=ALICE))
    bob = rows_of(client.get("/api/certificates/export", headers=BOB))
    assert alice == [
        {
            "learner_name": "Alex Lee",
            "course_title": "Safety 101",
            "serial_number": "EAST-SAFETY-ALEX",
            "issued_at_local": "2026-01-11 00:30",
        }
    ]
    assert bob[0]["serial_number"] == "WEST-SAFETY-ALEX"
    assert bob[0]["issued_at_local"] == "2026-01-10 21:30"
    hidden = rows_of(
        client.get("/api/certificates/export", headers=ALICE, params={"q": "WEST-SAFETY-ALEX"})
    )
    assert hidden == []
    empty = rows_of(client.get("/api/certificates/export", headers=ALICE, params={"q": "nobody"}))
    assert empty == []
    invalid = client.get("/api/certificates/export", headers=ALICE, params={"sort": "issued_at"})
    assert invalid.status_code == 400


def test_repeated_export_matches_list_order(client):
    client.post(
        "/api/certificates/bulk-issue",
        headers={**ALICE, "Idempotency-Key": "export-issue"},
        json={"course_id": "course-east-safety"},
    )
    params = {"q": "", "sort": "learner_name", "order": "asc"}
    first = rows_of(client.get("/api/certificates/export", headers=ALICE, params=params))
    second = rows_of(client.get("/api/certificates/export", headers=ALICE, params=params))
    assert first == second
    listed = []
    page = 1
    while True:
        payload = client.get(
            "/api/certificates",
            headers=ALICE,
            params={**params, "page": page, "page_size": 1},
        ).json()
        listed.extend(item["serial_number"] for item in payload["items"])
        if page * payload["page_size"] >= payload["total"]:
            break
        page += 1
    assert [row["serial_number"] for row in first] == listed


def test_small_volume_keeps_demo_rows_and_quotes_commas(client):
    inserted = generate_volume(os.environ["DATABASE_URL"], 3)
    assert inserted == 3
    assert generate_volume(os.environ["DATABASE_URL"], 3) == 0
    demo = client.get("/api/certificates/cert-east-alex", headers=ALICE)
    assert demo.status_code == 200
    assert demo.json()["issued_at_local"] == "2026-01-11 00:30"
    exported = rows_of(
        client.get(
            "/api/certificates/export",
            headers=ALICE,
            params={"q": "Target", "sort": "issued_date", "order": "desc"},
        )
    )
    assert [row["serial_number"] for row in exported] == [
        "EAST-VOL-00000000",
        "EAST-VOL-00000001",
        "EAST-VOL-00000002",
    ]
    assert exported[0]["learner_name"] == "Target Lee, Jr."
    assert len({row["issued_at_local"] for row in exported}) == 1
