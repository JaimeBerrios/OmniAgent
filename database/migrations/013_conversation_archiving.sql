-- OmniAgent: soporte para archivado de conversaciones.
-- No elimina mensajes ni modifica conversaciones existentes.

BEGIN;

ALTER TABLE conversations
    DROP CONSTRAINT conversations_status_check;

ALTER TABLE conversations
    ADD CONSTRAINT conversations_status_check
    CHECK (status IN ('open', 'closed', 'archived'));

CREATE INDEX IF NOT EXISTS
    idx_conversations_tenant_status
ON conversations (tenant_id, status);

COMMIT;
