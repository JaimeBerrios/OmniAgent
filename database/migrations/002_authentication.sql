
BEGIN;

CREATE TABLE users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT chk_users_email_normalized
        CHECK (email = LOWER(TRIM(email)))
);

CREATE TABLE memberships (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    tenant_id BIGINT NOT NULL REFERENCES tenants(id),
    role VARCHAR(20) NOT NULL DEFAULT 'agent',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_memberships_user_tenant
        UNIQUE (user_id, tenant_id),

    CONSTRAINT chk_memberships_role
        CHECK (role IN ('owner', 'admin', 'agent'))
);

CREATE INDEX idx_memberships_tenant
    ON memberships(tenant_id);

COMMIT;
