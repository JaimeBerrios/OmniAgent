CREATE TABLE IF NOT EXISTS messenger_outbound_deliveries (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    tenant_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,

    page_id VARCHAR(100) NOT NULL,
    recipient_psid VARCHAR(150) NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,

    meta_message_id VARCHAR(255),
    claim_token UUID,
    claimed_at TIMESTAMPTZ,

    last_error TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_messenger_outbound_message
        FOREIGN KEY (tenant_id, message_id)
        REFERENCES messages(tenant_id, id),

    CONSTRAINT fk_messenger_outbound_page
        FOREIGN KEY (tenant_id, page_id)
        REFERENCES messenger_pages(tenant_id, page_id),

    CONSTRAINT uq_messenger_outbound_message
        UNIQUE (tenant_id, message_id),

    CONSTRAINT chk_messenger_outbound_status
        CHECK (
            status IN (
                'pending',
                'sending',
                'sent',
                'failed',
                'unknown'
            )
        ),

    CONSTRAINT chk_messenger_outbound_attempts
        CHECK (attempts >= 0)
);

CREATE INDEX IF NOT EXISTS idx_messenger_outbound_pending
ON messenger_outbound_deliveries (status, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_messenger_outbound_claim_token
ON messenger_outbound_deliveries (claim_token)
WHERE claim_token IS NOT NULL;
