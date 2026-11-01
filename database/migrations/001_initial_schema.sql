
BEGIN;

CREATE TABLE tenants (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE customers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenants(id),
    external_id VARCHAR(150) NOT NULL,
    name VARCHAR(150),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, external_id),
    UNIQUE (tenant_id, id)
);

CREATE TABLE conversations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenants(id),
    customer_id BIGINT NOT NULL,
    channel VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers(tenant_id, id),
    CHECK (status IN ('open', 'closed'))
);

CREATE TABLE messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenants(id),
    conversation_id BIGINT NOT NULL,
    direction VARCHAR(10) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (tenant_id, conversation_id)
        REFERENCES conversations(tenant_id, id),
    CHECK (direction IN ('inbound', 'outbound'))
);

CREATE INDEX idx_customers_tenant
    ON customers(tenant_id);

CREATE INDEX idx_conversations_customer
    ON conversations(tenant_id, customer_id);

CREATE INDEX idx_messages_conversation
    ON messages(tenant_id, conversation_id, created_at);

COMMIT;
