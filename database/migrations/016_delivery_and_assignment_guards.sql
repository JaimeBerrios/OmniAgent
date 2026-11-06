-- Legacy interrupted sends must never be silently retried.
UPDATE whatsapp_outbound_deliveries
SET status = 'unknown', claim_token = NULL, claimed_at = NULL,
    last_error = 'Entrega heredada sin propiedad confirmada; requiere revisión', updated_at = NOW()
WHERE status = 'sending' AND (claim_token IS NULL OR claimed_at IS NULL);
ALTER TABLE conversations ADD CONSTRAINT fk_conversation_assignee_membership
 FOREIGN KEY (assigned_user_id, tenant_id) REFERENCES memberships(user_id, tenant_id);
CREATE INDEX idx_messages_cursor ON messages(tenant_id, conversation_id, id);
