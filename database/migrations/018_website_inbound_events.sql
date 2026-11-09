-- Transactional website outbox; composite keys preserve tenant ownership.
ALTER TABLE messages ADD CONSTRAINT uq_messages_conversation_source UNIQUE (tenant_id, conversation_id, id);
CREATE TABLE website_inbound_events (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tenant_id BIGINT NOT NULL REFERENCES tenants(id),
 site_id BIGINT NOT NULL,
 conversation_id BIGINT NOT NULL,
 message_id BIGINT NOT NULL,
 status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','processed','failed','cancelled')),
 attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 next_retry_at TIMESTAMPTZ DEFAULT NOW(),
 processing_started_at TIMESTAMPTZ,
 processed_at TIMESTAMPTZ,
 claim_token UUID,
 last_error TEXT,
 UNIQUE (tenant_id, message_id),
 FOREIGN KEY (tenant_id, site_id) REFERENCES website_sites(tenant_id, id),
 FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations(tenant_id, id),
 FOREIGN KEY (tenant_id, conversation_id, message_id) REFERENCES messages(tenant_id, conversation_id, id),
 CHECK ((status = 'processing') = (claim_token IS NOT NULL AND processing_started_at IS NOT NULL))
);
CREATE INDEX idx_website_events_pending ON website_inbound_events(next_retry_at, id) WHERE status IN ('pending','failed');
CREATE INDEX idx_website_events_processing ON website_inbound_events(processing_started_at) WHERE status = 'processing';
CREATE INDEX idx_website_events_tenant ON website_inbound_events(tenant_id, conversation_id);
CREATE UNIQUE INDEX uq_website_claim_token ON website_inbound_events(claim_token) WHERE claim_token IS NOT NULL;
