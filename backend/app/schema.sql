CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    timezone TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admins (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants (id),
    email TEXT NOT NULL UNIQUE,
    token TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants (id),
    title TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learners (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants (id),
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS enrollments (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants (id),
    course_id TEXT NOT NULL REFERENCES courses (id),
    learner_id TEXT NOT NULL REFERENCES learners (id),
    status TEXT NOT NULL CHECK (status IN ('completed', 'incomplete')),
    CONSTRAINT enrollments_course_learner_unique UNIQUE (tenant_id, course_id, learner_id)
);

CREATE TABLE IF NOT EXISTS certificates (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants (id),
    course_id TEXT NOT NULL REFERENCES courses (id),
    learner_id TEXT NOT NULL REFERENCES learners (id),
    serial_number TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    local_issued_at TEXT NOT NULL,
    local_issued_date DATE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
    CONSTRAINT certificates_serial_unique UNIQUE (serial_number),
    CONSTRAINT certificates_learner_course_unique UNIQUE (tenant_id, course_id, learner_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants (id),
    certificate_id TEXT NOT NULL REFERENCES certificates (id),
    action TEXT NOT NULL CHECK (action IN ('issued', 'revoked')),
    actor_email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT audit_events_certificate_action_unique UNIQUE (certificate_id, action)
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    tenant_id TEXT NOT NULL REFERENCES tenants (id),
    actor_id TEXT NOT NULL REFERENCES admins (id),
    idem_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('processing', 'completed')),
    http_status INTEGER,
    response_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT idempotency_keys_pkey PRIMARY KEY (tenant_id, actor_id, idem_key)
);

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_certificates_tenant_date
    ON certificates (tenant_id, local_issued_date, id);

CREATE INDEX IF NOT EXISTS idx_certificates_tenant_serial
    ON certificates (tenant_id, serial_number);

CREATE INDEX IF NOT EXISTS idx_learners_tenant_name
    ON learners (tenant_id, name);

CREATE INDEX IF NOT EXISTS idx_enrollments_course
    ON enrollments (tenant_id, course_id);
