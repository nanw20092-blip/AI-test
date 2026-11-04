from datetime import datetime, timezone

import psycopg

from app.timeutil import local_parts

VOLUME_COUNT = 100_000
VOLUME_META_KEY = "volume_east_rows"
# 02:00 UTC is 12:00 in Sydney during Australian standard time.
VOLUME_INSTANT = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)
TARGET_NAME_COUNT = 1_000


def generate_volume(dsn: str, count: int = VOLUME_COUNT) -> int:
    """Add East certificates without changing the seeded demo rows.

    Returns the number of rows inserted. A second call inserts nothing.
    """
    if count < 1:
        raise ValueError("count must be positive")
    local_at, local_date = local_parts(VOLUME_INSTANT, "Australia/Sydney")
    issued_at = VOLUME_INSTANT.strftime("%Y-%m-%d %H:%M:%S+00")
    issued_day = local_date.isoformat()

    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            existing = conn.execute(
                "SELECT value FROM app_meta WHERE key = %s",
                (VOLUME_META_KEY,),
            ).fetchone()
            if existing:
                return 0
            course = conn.execute(
                "SELECT id FROM courses WHERE id = %s",
                ("course-east-safety",),
            ).fetchone()
            if course is None:
                raise RuntimeError(
                    "Demo data is missing. Run python start.py --no-serve first."
                )
            _copy_learners(conn, count)
            _copy_enrollments(conn, count)
            _copy_certificates(conn, count, issued_at, local_at, issued_day)
            _copy_audits(conn, count, issued_at)
            conn.execute(
                "INSERT INTO app_meta (key, value) VALUES (%s, %s)",
                (VOLUME_META_KEY, str(count)),
            )
    return count


def _learner_name(index: int) -> str:
    if index == 0:
        return "Target Lee, Jr."
    if index < TARGET_NAME_COUNT:
        return "Target Lee"
    return "Pat Lee"


def _copy_learners(conn, count: int) -> None:
    with conn.cursor() as cur:
        with cur.copy(
            "COPY learners (id, tenant_id, name) FROM STDIN WITH (FORMAT TEXT)"
        ) as copy:
            for index in range(count):
                copy.write_row(
                    (f"learner-vol-{index:08d}", "east", _learner_name(index))
                )


def _copy_enrollments(conn, count: int) -> None:
    with conn.cursor() as cur:
        with cur.copy(
            """
            COPY enrollments (id, tenant_id, course_id, learner_id, status)
            FROM STDIN WITH (FORMAT TEXT)
            """
        ) as copy:
            for index in range(count):
                copy.write_row(
                    (
                        f"enr-vol-{index:08d}",
                        "east",
                        "course-east-safety",
                        f"learner-vol-{index:08d}",
                        "completed",
                    )
                )


def _copy_certificates(conn, count: int, issued_at: str, local_at: str, issued_day: str) -> None:
    with conn.cursor() as cur:
        with cur.copy(
            """
            COPY certificates (
                id, tenant_id, course_id, learner_id, serial_number,
                issued_at, local_issued_at, local_issued_date, status
            ) FROM STDIN WITH (FORMAT TEXT)
            """
        ) as copy:
            for index in range(count):
                copy.write_row(
                    (
                        f"cert-vol-{index:08d}",
                        "east",
                        "course-east-safety",
                        f"learner-vol-{index:08d}",
                        f"EAST-VOL-{index:08d}",
                        issued_at,
                        local_at,
                        issued_day,
                        "active",
                    )
                )


def _copy_audits(conn, count: int, issued_at: str) -> None:
    with conn.cursor() as cur:
        with cur.copy(
            """
            COPY audit_events (
                tenant_id, certificate_id, action, actor_email, created_at
            ) FROM STDIN WITH (FORMAT TEXT)
            """
        ) as copy:
            for index in range(count):
                copy.write_row(
                    (
                        "east",
                        f"cert-vol-{index:08d}",
                        "issued",
                        "alice@east.test",
                        issued_at,
                    )
                )
