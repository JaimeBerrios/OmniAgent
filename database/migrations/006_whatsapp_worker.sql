-- Seguimiento de procesamiento y reintentos.

ALTER TABLE whatsapp_inbound_events
    ADD COLUMN IF NOT EXISTS message_body TEXT,
    ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_error TEXT;

-- Evitar contadores negativos.
ALTER TABLE whatsapp_inbound_events
    ADD CONSTRAINT chk_whatsapp_attempts
    CHECK (attempts >= 0);

-- Optimizar la búsqueda de mensajes pendientes.
CREATE INDEX IF NOT EXISTS idx_whatsapp_worker_queue
ON whatsapp_inbound_events (
    status,
    next_retry_at,
    created_at
);

-- Recuperar eventos pendientes existentes.
UPDATE whatsapp_inbound_events
SET next_retry_at = NOW()
WHERE status IN ('pending', 'failed')
  AND next_retry_at IS NULL;
