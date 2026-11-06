CREATE TABLE IF NOT EXISTS whatsapp_outbound_deliveries (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    tenant_id BIGINT NOT NULL
        REFERENCES tenants(id),

    message_id BIGINT NOT NULL,

    recipient_phone VARCHAR(30) NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'pending',

    attempts INTEGER NOT NULL DEFAULT 0,

    meta_message_id VARCHAR(255),

    last_error TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_outbound_message
        FOREIGN KEY (tenant_id, message_id)
        REFERENCES messages(tenant_id, id),

    CONSTRAINT uq_outbound_delivery_message
        UNIQUE (tenant_id, message_id),

    CONSTRAINT chk_outbound_delivery_status
        CHECK (
            status IN (
                'pending',
                'sending',
                'sent',
                'failed',
                'unknown'
            )
        ),

    CONSTRAINT chk_outbound_attempts
        CHECK (attempts >= 0)
);

CREATE INDEX IF NOT EXISTS idx_outbound_delivery_status
ON whatsapp_outbound_deliveries (status, created_at);
