import csv
import hashlib
import io
import json
import logging
import secrets
import uuid
from datetime import datetime, timezone

from psycopg import errors
from psycopg.types.json import Jsonb

from app.db import get_pool
from app.timeutil import iso_z, local_parts

logger = logging.getLogger(__name__)

SORT_COLUMNS = {
    "learner_name": "l.name",
    "serial_number": "c.serial_number",
    "issued_date": "c.local_issued_date",
    "course_title": "co.title",
    "status": "c.status",
}


class RequestError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(detail)


def canonical_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_actor(token: str) -> dict | None:
    with get_pool().connection() as conn:
        row = conn.execute(
            """
            SELECT a.id, a.email, a.tenant_id, t.name AS tenant_name, t.timezone
            FROM admins a
            JOIN tenants t ON t.id = a.tenant_id
            WHERE a.token = %s
            """,
            (token,),
        ).fetchone()
    return dict(row) if row else None


def list_actors() -> list[dict]:
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT a.email, a.token, a.tenant_id, t.name AS tenant_name, t.timezone
            FROM admins a
            JOIN tenants t ON t.id = a.tenant_id
            ORDER BY t.name, a.email
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_courses(actor: dict) -> list[dict]:
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title
            FROM courses
            WHERE tenant_id = %s
            ORDER BY title, id
            """,
            (actor["tenant_id"],),
        ).fetchall()
    return [dict(row) for row in rows]


def _like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _certificate_query(actor: dict, q: str, sort: str, order: str) -> tuple[str, tuple, str]:
    if sort not in SORT_COLUMNS:
        raise RequestError(400, "Invalid sort field")
    if order not in {"asc", "desc"}:
        raise RequestError(400, "Invalid sort order")
    pattern = _like_pattern(q)
    where = """
        WHERE c.tenant_id = %s
          AND (
                %s = ''
                OR l.name ILIKE %s ESCAPE '\\'
                OR c.serial_number ILIKE %s ESCAPE '\\'
              )
    """
    params = (actor["tenant_id"], q, pattern, pattern)
    # sort and order are whitelisted above, so they are not user SQL.
    order_by = f"ORDER BY {SORT_COLUMNS[sort]} {order}, c.id ASC"
    return where, params, order_by


def list_certificates(
    actor: dict,
    *,
    q: str,
    sort: str,
    order: str,
    page: int,
    page_size: int,
) -> dict:
    if page < 1 or page_size < 1 or page_size > 100:
        raise RequestError(400, "Invalid page")
    where, params, order_by = _certificate_query(actor, q, sort, order)
    list_sql = f"""
        SELECT c.id, c.serial_number, co.title AS course, l.name AS learner,
               c.local_issued_at AS issued_at_local, c.issued_at, c.status
        FROM certificates c
        JOIN learners l ON l.id = c.learner_id
        JOIN courses co ON co.id = c.course_id
        {where}
        {order_by}
        LIMIT %s OFFSET %s
    """
    count_sql = f"""
        SELECT COUNT(*) AS total
        FROM certificates c
        JOIN learners l ON l.id = c.learner_id
        JOIN courses co ON co.id = c.course_id
        {where}
    """
    offset = (page - 1) * page_size
    with get_pool().connection() as conn:
        total = conn.execute(count_sql, params).fetchone()["total"]
        rows = conn.execute(list_sql, (*params, page_size, offset)).fetchall()
    return {
        "items": [_certificate_summary(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def validate_certificate_query(actor: dict, q: str, sort: str, order: str) -> None:
    _certificate_query(actor, q, sort, order)


def iter_certificate_csv(actor: dict, *, q: str, sort: str, order: str):
    """Yield CSV text. The first yield happens after the read cursor is open."""
    where, params, order_by = _certificate_query(actor, q, sort, order)
    query = f"""
        SELECT l.name AS learner_name, co.title AS course_title,
               c.serial_number, c.local_issued_at AS issued_at_local
        FROM certificates c
        JOIN learners l ON l.id = c.learner_id
        JOIN courses co ON co.id = c.course_id
        {where}
        {order_by}
    """
    header = _csv_line(
        ["learner_name", "course_title", "serial_number", "issued_at_local"]
    )
    with get_pool().connection() as conn:
        with conn.transaction():
            cursor_name = "exp_" + uuid.uuid4().hex
            with conn.cursor(name=cursor_name) as cur:
                cur.itersize = 2000
                cur.execute(query, params)
                yield header
                pending: list[str] = []
                for row in cur:
                    pending.append(
                        _csv_line(
                            [
                                row["learner_name"],
                                row["course_title"],
                                row["serial_number"],
                                row["issued_at_local"],
                            ]
                        )
                    )
                    if len(pending) >= 500:
                        yield "".join(pending)
                        pending.clear()
                if pending:
                    yield "".join(pending)


def _csv_line(values: list[str]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerow(values)
    return buffer.getvalue()


def get_certificate(actor: dict, certificate_id: str) -> dict:
    with get_pool().connection() as conn:
        detail = _load_detail(conn, actor["tenant_id"], certificate_id)
    if detail is None:
        raise RequestError(404, "Not found")
    return detail


def revoke_certificate(actor: dict, certificate_id: str) -> dict:
    with get_pool().connection() as conn:
        with conn.transaction():
            conn.execute("SET LOCAL lock_timeout = '10s'")
            row = conn.execute(
                """
                SELECT id, status
                FROM certificates
                WHERE id = %s AND tenant_id = %s
                FOR UPDATE
                """,
                (certificate_id, actor["tenant_id"]),
            ).fetchone()
            if row is None:
                raise RequestError(404, "Not found")
            changed = False
            if row["status"] == "active":
                conn.execute(
                    "UPDATE certificates SET status = 'revoked' WHERE id = %s",
                    (certificate_id,),
                )
                conn.execute(
                    """
                    INSERT INTO audit_events (tenant_id, certificate_id, action, actor_email)
                    VALUES (%s, %s, 'revoked', %s)
                    """,
                    (actor["tenant_id"], certificate_id, actor["email"]),
                )
                changed = True
            detail = _load_detail(conn, actor["tenant_id"], certificate_id)
    detail["changed"] = changed
    return detail


def bulk_issue(actor: dict, idem_key: str, payload: dict) -> tuple[int, dict]:
    request_hash = canonical_hash(payload)
    with get_pool().connection() as conn:
        with conn.transaction():
            conn.execute("SET LOCAL lock_timeout = '10s'")
            claimed = conn.execute(
                """
                INSERT INTO idempotency_keys (
                    tenant_id, actor_id, idem_key, request_hash, status
                ) VALUES (%s, %s, %s, %s, 'processing')
                ON CONFLICT DO NOTHING
                RETURNING idem_key
                """,
                (actor["tenant_id"], actor["id"], idem_key, request_hash),
            ).fetchone()
            if claimed is None:
                existing = conn.execute(
                    """
                    SELECT request_hash, status, http_status, response_json
                    FROM idempotency_keys
                    WHERE tenant_id = %s AND actor_id = %s AND idem_key = %s
                    FOR UPDATE
                    """,
                    (actor["tenant_id"], actor["id"], idem_key),
                ).fetchone()
                if existing["request_hash"] != request_hash:
                    raise RequestError(
                        409,
                        "Idempotency key reuse with a different request payload",
                    )
                if existing["status"] != "completed":
                    raise RequestError(409, "Idempotency key is already in progress")
                return int(existing["http_status"]), existing["response_json"]

            status, body = _issue_course(conn, actor, payload["course_id"])
            conn.execute(
                """
                UPDATE idempotency_keys
                SET status = 'completed', http_status = %s, response_json = %s
                WHERE tenant_id = %s AND actor_id = %s AND idem_key = %s
                """,
                (
                    status,
                    Jsonb(body),
                    actor["tenant_id"],
                    actor["id"],
                    idem_key,
                ),
            )
            return status, body


def _issue_course(conn, actor: dict, course_id: str) -> tuple[int, dict]:
    course = conn.execute(
        """
        SELECT id, title
        FROM courses
        WHERE id = %s AND tenant_id = %s
        """,
        (course_id, actor["tenant_id"]),
    ).fetchone()
    if course is None:
        return 404, {"detail": "Not found"}

    enrollments = conn.execute(
        """
        SELECT e.learner_id, l.name AS learner_name, e.status,
               c.id AS certificate_id, c.serial_number
        FROM enrollments e
        JOIN learners l ON l.id = e.learner_id
        LEFT JOIN certificates c
          ON c.tenant_id = e.tenant_id
         AND c.course_id = e.course_id
         AND c.learner_id = e.learner_id
        WHERE e.tenant_id = %s AND e.course_id = %s
        ORDER BY l.name ASC, e.learner_id ASC
        FOR UPDATE OF e
        """,
        (actor["tenant_id"], course_id),
    ).fetchall()

    results = []
    for enrollment in enrollments:
        results.append(_issue_learner(conn, actor, course_id, enrollment))
    return 200, {
        "status": "completed",
        "course_id": course["id"],
        "course_title": course["title"],
        "results": results,
    }


def _issue_learner(conn, actor: dict, course_id: str, enrollment: dict) -> dict:
    base = {
        "learner_id": enrollment["learner_id"],
        "learner_name": enrollment["learner_name"],
        "serial_number": None,
    }
    if enrollment["status"] != "completed":
        return {**base, "outcome": "skipped", "reason": "not_completed"}
    if enrollment["certificate_id"]:
        return {
            **base,
            "outcome": "skipped",
            "reason": "already_certified",
            "serial_number": enrollment["serial_number"],
        }

    for attempt in range(5):
        certificate_id = str(uuid.uuid4())
        serial = "CERT-" + secrets.token_hex(8).upper()
        issued_at = datetime.now(timezone.utc)
        local_at, local_date = local_parts(issued_at, actor["timezone"])
        try:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO certificates (
                        id, tenant_id, course_id, learner_id, serial_number,
                        issued_at, local_issued_at, local_issued_date, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active')
                    """,
                    (
                        certificate_id,
                        actor["tenant_id"],
                        course_id,
                        enrollment["learner_id"],
                        serial,
                        issued_at,
                        local_at,
                        local_date,
                        ),
                )
                conn.execute(
                    """
                    INSERT INTO audit_events (
                        tenant_id, certificate_id, action, actor_email, created_at
                    ) VALUES (%s, %s, 'issued', %s, %s)
                    """,
                    (actor["tenant_id"], certificate_id, actor["email"], issued_at),
                )
            return {**base, "outcome": "issued", "reason": None, "serial_number": serial}
        except errors.UniqueViolation as exc:
            constraint = exc.diag.constraint_name if exc.diag else None
            if constraint == "certificates_learner_course_unique":
                existing = conn.execute(
                    """
                    SELECT serial_number
                    FROM certificates
                    WHERE tenant_id = %s AND course_id = %s AND learner_id = %s
                    """,
                    (actor["tenant_id"], course_id, enrollment["learner_id"]),
                ).fetchone()
                return {
                    **base,
                    "outcome": "skipped",
                    "reason": "already_certified",
                    "serial_number": existing["serial_number"] if existing else None,
                }
            if constraint == "certificates_serial_unique" and attempt < 4:
                continue
            logger.exception("certificate insert conflict")
            return {**base, "outcome": "failed", "reason": "issuance_failed"}
        except Exception:
            logger.exception("certificate issuance failed")
            return {**base, "outcome": "failed", "reason": "issuance_failed"}
    return {**base, "outcome": "failed", "reason": "issuance_failed"}


def _load_detail(conn, tenant_id: str, certificate_id: str) -> dict | None:
    row = conn.execute(
        """
        SELECT c.id, c.serial_number, co.title AS course, l.name AS learner,
               c.local_issued_at AS issued_at_local, c.issued_at, c.status
        FROM certificates c
        JOIN learners l ON l.id = c.learner_id
        JOIN courses co ON co.id = c.course_id
        WHERE c.id = %s AND c.tenant_id = %s
        """,
        (certificate_id, tenant_id),
    ).fetchone()
    if row is None:
        return None
    audits = conn.execute(
        """
        SELECT action, actor_email, created_at
        FROM audit_events
        WHERE certificate_id = %s AND tenant_id = %s
        ORDER BY id ASC
        """,
        (certificate_id, tenant_id),
    ).fetchall()
    detail = _certificate_summary(row)
    detail["audits"] = [
        {
            "action": audit["action"],
            "actor_email": audit["actor_email"],
            "created_at": iso_z(audit["created_at"]),
        }
        for audit in audits
    ]
    return detail


def _certificate_summary(row: dict) -> dict:
    return {
        "id": row["id"],
        "serial_number": row["serial_number"],
        "course": row["course"],
        "learner": row["learner"],
        "issued_at_local": row["issued_at_local"],
        "issued_at_utc": iso_z(row["issued_at"]),
        "status": row["status"],
    }
