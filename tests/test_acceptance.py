import os

os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/audi_test"

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.bootstrap import apply_schema, ensure_database, truncate_and_seed
from app.db import close_pool, get_pool, init_pool
from app.main import app
from app.services import bulk_issue, fetch_actor
from app.timeutil import local_parts


ALICE = {"X-Actor-Token": "east-alice"}
BOB = {"X-Actor-Token": "west-bob"}


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


def query_one(statement: str, params: tuple = ()):
    with get_pool().connection() as conn:
        return conn.execute(statement, params).fetchone()


def count(statement: str, params: tuple = ()) -> int:
    return query_one(statement, params)["n"]


def test_sydney_and_perth_local_times():
    issued = datetime(2026, 1, 10, 13, 30, tzinfo=timezone.utc)
    east, east_day = local_parts(issued, "Australia/Sydney")
    west, west_day = local_parts(issued, "Australia/Perth")
    assert east == "2026-01-11 00:30"
    assert str(east_day) == "2026-01-11"
    assert west == "2026-01-10 21:30"
    assert str(west_day) == "2026-01-10"


def test_tenant_isolation_on_list_detail_and_bulk_issue(client):
    alice_list = client.get("/api/certificates", headers=ALICE)
    bob_list = client.get("/api/certificates", headers=BOB)
    assert alice_list.status_code == 200
    assert bob_list.status_code == 200
    alice_serials = {item["serial_number"] for item in alice_list.json()["items"]}
    bob_serials = {item["serial_number"] for item in bob_list.json()["items"]}
    assert alice_serials == {"EAST-SAFETY-ALEX"}
    assert bob_serials == {"WEST-SAFETY-ALEX"}

    assert client.get("/api/certificates/cert-east-alex", headers=BOB).status_code == 404
    east_before = count("SELECT COUNT(*) AS n FROM certificates WHERE tenant_id = 'east'")
    audits_before = count("SELECT COUNT(*) AS n FROM audit_events WHERE tenant_id = 'east'")
    rejected = client.post(
        "/api/certificates/bulk-issue",
        headers={**BOB, "Idempotency-Key": "bob-cross-tenant"},
        json={"course_id": "course-east-safety"},
    )
    assert rejected.status_code == 404
    assert rejected.json()["detail"] == "Not found"
    assert count("SELECT COUNT(*) AS n FROM certificates WHERE tenant_id = 'east'") == east_before
    assert count("SELECT COUNT(*) AS n FROM audit_events WHERE tenant_id = 'east'") == audits_before

    own_course = client.get("/api/courses", headers=BOB)
    assert own_course.json()["courses"] == [{"id": "course-west-safety", "title": "Safety 101"}]


def test_local_issue_time_and_calendar_date_sort(client):
    east = client.get("/api/certificates/cert-east-alex", headers=ALICE).json()
    west = client.get("/api/certificates/cert-west-alex", headers=BOB).json()
    assert east["issued_at_utc"] == "2026-01-10T13:30:00Z"
    assert west["issued_at_utc"] == "2026-01-10T13:30:00Z"
    assert east["issued_at_local"] == "2026-01-11 00:30"
    assert west["issued_at_local"] == "2026-01-10 21:30"

    early = datetime(2026, 1, 10, 13, 30, tzinfo=timezone.utc)
    late = datetime(2026, 1, 10, 23, 0, tzinfo=timezone.utc)
    early_local, early_day = local_parts(early, "Australia/Sydney")
    late_local, late_day = local_parts(late, "Australia/Sydney")
    assert early_day == late_day
    with get_pool().connection() as conn:
        with conn.transaction():
            conn.execute(
                "INSERT INTO learners (id, tenant_id, name) VALUES (%s, 'east', %s)",
                ("learner-sort-aaa", "Sort A"),
            )
            conn.execute(
                "INSERT INTO learners (id, tenant_id, name) VALUES (%s, 'east', %s)",
                ("learner-sort-zzz", "Sort Z"),
            )
            conn.execute(
                """
                INSERT INTO certificates (
                    id, tenant_id, course_id, learner_id, serial_number,
                    issued_at, local_issued_at, local_issued_date, status
                ) VALUES
                    ('cert-zzz', 'east', 'course-east-safety', 'learner-sort-zzz',
                     'EAST-SORT-EARLY', %s, %s, %s, 'active'),
                    ('cert-aaa', 'east', 'course-east-safety', 'learner-sort-aaa',
                     'EAST-SORT-LATE', %s, %s, %s, 'active')
                """,
                (early, early_local, early_day, late, late_local, late_day),
            )

    listed = client.get(
        "/api/certificates",
        headers=ALICE,
        params={"q": "Sort", "sort": "issued_date", "order": "asc"},
    )
    assert [item["id"] for item in listed.json()["items"]] == ["cert-aaa", "cert-zzz"]
    listed_desc = client.get(
        "/api/certificates",
        headers=ALICE,
        params={"q": "Sort", "sort": "issued_date", "order": "desc"},
    )
    assert [item["id"] for item in listed_desc.json()["items"]] == ["cert-aaa", "cert-zzz"]


def test_search_pagination_and_empty(client):
    found = client.get("/api/certificates", headers=ALICE, params={"q": "alex lee"})
    assert found.json()["total"] == 1
    assert found.json()["items"][0]["serial_number"] == "EAST-SAFETY-ALEX"
    by_serial = client.get(
        "/api/certificates",
        headers=ALICE,
        params={"q": "EAST-SAFETY-ALEX"},
    )
    assert by_serial.json()["total"] == 1
    empty = client.get("/api/certificates", headers=ALICE, params={"q": "nobody"})
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert empty.json()["total"] == 0
    hidden = client.get(
        "/api/certificates",
        headers=ALICE,
        params={"q": "WEST-SAFETY-ALEX"},
    )
    assert hidden.json()["total"] == 0
    invalid = client.get("/api/certificates", headers=ALICE, params={"sort": "issued_at"})
    assert invalid.status_code == 400


def test_bulk_issue_outcomes_and_repeat_with_new_key(client):
    first = client.post(
        "/api/certificates/bulk-issue",
        headers={**ALICE, "Idempotency-Key": "issue-1"},
        json={"course_id": "course-east-safety"},
    )
    assert first.status_code == 200
    by_name = {row["learner_name"]: row for row in first.json()["results"]}
    assert by_name["Alex Lee"]["outcome"] == "skipped"
    assert by_name["Alex Lee"]["reason"] == "already_certified"
    assert by_name["Casey Ng"]["outcome"] == "issued"
    assert by_name["Casey Ng"]["serial_number"]
    assert by_name["Drew Kim"]["outcome"] == "skipped"
    assert by_name["Drew Kim"]["reason"] == "not_completed"

    drew = query_one(
        """
        SELECT c.id
        FROM certificates c
        JOIN learners l ON l.id = c.learner_id
        WHERE l.name = 'Drew Kim' AND c.tenant_id = 'east'
        """
    )
    assert drew is None
    casey_audits = count(
        """
        SELECT COUNT(*) AS n
        FROM audit_events a
        JOIN certificates c ON c.id = a.certificate_id
        JOIN learners l ON l.id = c.learner_id
        WHERE l.name = 'Casey Ng' AND a.action = 'issued'
        """
    )
    assert casey_audits == 1

    second = client.post(
        "/api/certificates/bulk-issue",
        headers={**ALICE, "Idempotency-Key": "issue-2"},
        json={"course_id": "course-east-safety"},
    )
    second_by_name = {row["learner_name"]: row for row in second.json()["results"]}
    assert second_by_name["Casey Ng"]["outcome"] == "skipped"
    assert second_by_name["Casey Ng"]["reason"] == "already_certified"
    assert casey_audits == count(
        """
        SELECT COUNT(*) AS n
        FROM audit_events a
        JOIN certificates c ON c.id = a.certificate_id
        JOIN learners l ON l.id = c.learner_id
        WHERE l.name = 'Casey Ng' AND a.action = 'issued'
        """
    )


def test_same_idempotency_key_replays_one_operation(client):
    headers = {**ALICE, "Idempotency-Key": "same-key"}
    body = {"course_id": "course-east-safety"}
    first = client.post("/api/certificates/bulk-issue", headers=headers, json=body)
    second = client.post("/api/certificates/bulk-issue", headers=headers, json=body)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert count(
        "SELECT COUNT(*) AS n FROM certificates WHERE tenant_id = 'east'"
    ) == 2


def test_concurrent_same_idempotency_key_issues_once(seeded):
    actor = fetch_actor("east-alice")
    payload = {"course_id": "course-east-safety"}

    def call():
        return bulk_issue(actor, "concurrent-key", payload)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = [future.result() for future in [pool.submit(call) for _ in range(8)]]

    assert {status for status, _body in results} == {200}
    assert all(body == results[0][1] for _status, body in results)
    issued = [row for row in results[0][1]["results"] if row["outcome"] == "issued"]
    assert len(issued) == 1
    assert count(
        """
        SELECT COUNT(*) AS n
        FROM certificates c
        JOIN learners l ON l.id = c.learner_id
        WHERE l.name = 'Casey Ng' AND c.tenant_id = 'east'
        """
    ) == 1
    assert count(
        """
        SELECT COUNT(*) AS n
        FROM audit_events a
        JOIN certificates c ON c.id = a.certificate_id
        JOIN learners l ON l.id = c.learner_id
        WHERE l.name = 'Casey Ng' AND a.action = 'issued'
        """
    ) == 1


def test_reused_idempotency_key_with_different_payload_conflicts(client):
    headers = {**ALICE, "Idempotency-Key": "reuse-key"}
    first = client.post(
        "/api/certificates/bulk-issue",
        headers=headers,
        json={"course_id": "course-east-safety"},
    )
    conflict = client.post(
        "/api/certificates/bulk-issue",
        headers=headers,
        json={"course_id": "course-west-safety"},
    )
    replay = client.post(
        "/api/certificates/bulk-issue",
        headers=headers,
        json={"course_id": "course-east-safety"},
    )
    assert first.status_code == 200
    assert conflict.status_code == 409
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert count("SELECT COUNT(*) AS n FROM certificates WHERE tenant_id = 'west'") == 1
    assert count("SELECT COUNT(*) AS n FROM certificates WHERE tenant_id = 'east'") == 2


def test_revoke_writes_one_audit_and_repeat_does_not(client):
    first = client.post("/api/certificates/cert-east-alex/revoke", headers=ALICE)
    second = client.post("/api/certificates/cert-east-alex/revoke", headers=ALICE)
    assert first.status_code == 200
    assert first.json()["status"] == "revoked"
    assert first.json()["changed"] is True
    assert second.json()["changed"] is False
    assert second.json()["status"] == "revoked"
    actions = [audit["action"] for audit in second.json()["audits"]]
    assert actions == ["issued", "revoked"]
    assert count(
        """
        SELECT COUNT(*) AS n FROM audit_events
        WHERE certificate_id = 'cert-east-alex' AND action = 'revoked'
        """
    ) == 1

    cross = client.post("/api/certificates/cert-west-alex/revoke", headers=ALICE)
    assert cross.status_code == 404
    west = query_one("SELECT status FROM certificates WHERE id = 'cert-west-alex'")
    assert west["status"] == "active"
    assert count(
        """
        SELECT COUNT(*) AS n FROM audit_events
        WHERE certificate_id = 'cert-west-alex' AND action = 'revoked'
        """
    ) == 0


def test_missing_token_and_missing_idempotency_key(client):
    assert client.get("/api/certificates").status_code == 401
    assert client.get("/api/certificates", headers={"X-Actor-Token": "nope"}).status_code == 401
    before = count("SELECT COUNT(*) AS n FROM certificates")
    missing_key = client.post(
        "/api/certificates/bulk-issue",
        headers=ALICE,
        json={"course_id": "course-east-safety"},
    )
    assert missing_key.status_code == 400
    assert count("SELECT COUNT(*) AS n FROM certificates") == before
