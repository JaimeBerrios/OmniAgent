-- Identificador único de cada intento de procesamiento.
ALTER TABLE whatsapp_inbound_events
    ADD COLUMN IF NOT EXISTS claim_token UUID;

-- Facilitar la comprobación del propietario del trabajo.
CREATE INDEX IF NOT EXISTS idx_whatsapp_worker_claim
ON whatsapp_inbound_events (claim_token)
WHERE status = 'processing';
