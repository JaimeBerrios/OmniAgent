ALTER TABLE conversations ADD COLUMN assigned_user_id BIGINT REFERENCES users(id);
ALTER TABLE conversations ADD COLUMN last_read_message_id BIGINT;
ALTER TABLE conversations ADD COLUMN automation_enabled BOOLEAN NOT NULL DEFAULT TRUE;
CREATE INDEX idx_conversations_assignee ON conversations(tenant_id, assigned_user_id, id);
CREATE TABLE conversation_events (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tenant_id BIGINT NOT NULL,
 conversation_id BIGINT NOT NULL,
 actor_id BIGINT NOT NULL REFERENCES users(id),
 kind VARCHAR(30) NOT NULL,
 content TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations(tenant_id, id)
);
CREATE INDEX idx_conversation_events ON conversation_events(tenant_id, conversation_id, id);
CREATE TABLE admin_events (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tenant_id BIGINT NOT NULL REFERENCES tenants(id),
 actor_id BIGINT NOT NULL REFERENCES users(id),
 action VARCHAR(50) NOT NULL,
 target VARCHAR(150) NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
