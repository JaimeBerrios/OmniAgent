ALTER TABLE messages ADD COLUMN idempotency_key VARCHAR(100);
ALTER TABLE messages ADD CONSTRAINT uq_message_request UNIQUE (tenant_id, conversation_id, idempotency_key);
CREATE TABLE website_sites (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tenant_id BIGINT NOT NULL REFERENCES tenants(id),
 public_id VARCHAR(64) NOT NULL UNIQUE,
 name VARCHAR(150) NOT NULL,
 origin VARCHAR(255) NOT NULL,
 is_active BOOLEAN NOT NULL DEFAULT TRUE,
 UNIQUE (tenant_id, id)
);
CREATE INDEX idx_website_sites_tenant ON website_sites(tenant_id);
CREATE TABLE visitor_sessions (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tenant_id BIGINT NOT NULL,
 site_id BIGINT NOT NULL,
 conversation_id BIGINT NOT NULL,
 token_hash VARCHAR(64) NOT NULL UNIQUE,
 expires_at TIMESTAMPTZ NOT NULL,
 revoked_at TIMESTAMPTZ,
 FOREIGN KEY (tenant_id, site_id) REFERENCES website_sites(tenant_id, id),
 FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations(tenant_id, id)
);
CREATE INDEX idx_visitor_sessions_expiry ON visitor_sessions(expires_at);
CREATE TABLE request_limits (
 key VARCHAR(64) PRIMARY KEY,
 window_start TIMESTAMPTZ NOT NULL,
 count INTEGER NOT NULL
);
