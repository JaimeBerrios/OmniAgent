CREATE TABLE IF NOT EXISTS messenger_pages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenants(id),
    page_id VARCHAR(100) NOT NULL UNIQUE,
    page_name VARCHAR(150),
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, page_id)
);

CREATE TABLE IF NOT EXISTS messenger_inbound_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    page_id VARCHAR(100) NOT NULL,
    sender_psid VARCHAR(150) NOT NULL,
    meta_message_id VARCHAR(255) NOT NULL,
    message_body TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_retry_at TIMESTAMPTZ DEFAULT NOW(),
    processing_started_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    claim_token UUID,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_messenger_page
        FOREIGN KEY (tenant_id, page_id)
        REFERENCES messenger_pages(tenant_id, page_id),

    CONSTRAINT uq_messenger_message
        UNIQUE (page_id, meta_message_id),

    CONSTRAINT ck_messenger_status
        CHECK (status IN (
            'pending',
            'processing',
            'processed',
            'failed'
        )),

    CONSTRAINT ck_messenger_attempts
        CHECK (attempts >= 0)
);

CREATE INDEX IF NOT EXISTS idx_messenger_pending
ON messenger_inbound_events (
    status,
    next_retry_at
);

CREATE INDEX IF NOT EXISTS idx_messenger_tenant
ON messenger_inbound_events (
    tenant_id,
    created_at
);
