CREATE TABLE whatsapp_inbound_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    tenant_id BIGINT NOT NULL REFERENCES tenants(id),

    meta_message_id VARCHAR(255) NOT NULL,

    phone_number_id VARCHAR(100) NOT NULL,

    sender_phone VARCHAR(50) NOT NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'pending',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    processed_at TIMESTAMPTZ,

    CONSTRAINT uq_whatsapp_meta_message
        UNIQUE (phone_number_id, meta_message_id),

    CONSTRAINT chk_whatsapp_event_status
        CHECK (status IN ('pending', 'processing', 'processed', 'failed'))
);

CREATE INDEX idx_whatsapp_events_tenant
    ON whatsapp_inbound_events(tenant_id, created_at);
