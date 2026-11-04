from datetime import datetime, timezone

from app.timeutil import local_parts

DEMO_INSTANT = datetime(2026, 1, 10, 13, 30, tzinfo=timezone.utc)

TENANTS = (
    ("east", "East", "Australia/Sydney"),
    ("west", "West", "Australia/Perth"),
)

ADMINS = (
    ("admin-alice", "east", "alice@east.test", "east-alice"),
    ("admin-bob", "west", "bob@west.test", "west-bob"),
)

# Completed and already certified, completed and eligible, incomplete.
LEARNERS = (
    ("alex", "Alex Lee", "completed", True),
    ("casey", "Casey Ng", "completed", False),
    ("drew", "Drew Kim", "incomplete", False),
)


def insert_seed(conn) -> None:
    for tenant_id, name, tz_name in TENANTS:
        conn.execute(
            "INSERT INTO tenants (id, name, timezone) VALUES (%s, %s, %s)",
            (tenant_id, name, tz_name),
        )

    admin_email = {tenant_id: email for _, tenant_id, email, _ in ADMINS}
    for admin_id, tenant_id, email, token in ADMINS:
        conn.execute(
            """
            INSERT INTO admins (id, tenant_id, email, token)
            VALUES (%s, %s, %s, %s)
            """,
            (admin_id, tenant_id, email, token),
        )

    for tenant_id, _, tz_name in TENANTS:
        course_id = f"course-{tenant_id}-safety"
        conn.execute(
            "INSERT INTO courses (id, tenant_id, title) VALUES (%s, %s, %s)",
            (course_id, tenant_id, "Safety 101"),
        )
        local_at, local_date = local_parts(DEMO_INSTANT, tz_name)
        for slug, learner_name, status, certified in LEARNERS:
            learner_id = f"learner-{tenant_id}-{slug}"
            conn.execute(
                "INSERT INTO learners (id, tenant_id, name) VALUES (%s, %s, %s)",
                (learner_id, tenant_id, learner_name),
            )
            conn.execute(
                """
                INSERT INTO enrollments (id, tenant_id, course_id, learner_id, status)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (f"enr-{tenant_id}-{slug}", tenant_id, course_id, learner_id, status),
            )
            if not certified:
                continue
            certificate_id = f"cert-{tenant_id}-{slug}"
            serial = f"{tenant_id.upper()}-SAFETY-{slug.upper()}"
            conn.execute(
                """
                INSERT INTO certificates (
                    id, tenant_id, course_id, learner_id, serial_number,
                    issued_at, local_issued_at, local_issued_date, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active')
                """,
                (
                    certificate_id,
                    tenant_id,
                    course_id,
                    learner_id,
                    serial,
                    DEMO_INSTANT,
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
                (tenant_id, certificate_id, admin_email[tenant_id], DEMO_INSTANT),
            )


def seed_if_empty(conn) -> bool:
    row = conn.execute(
        "SELECT value FROM app_meta WHERE key = 'seed_version'"
    ).fetchone()
    if row:
        return False
    insert_seed(conn)
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES ('seed_version', '1')"
    )
    return True
