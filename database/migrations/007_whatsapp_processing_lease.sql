-- Registrar el inicio del procesamiento para recuperar
-- eventos interrumpidos por fallos del worker.

ALTER TABLE whatsapp_inbound_events
    ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ;

-- Optimizar la recuperación de eventos en procesamiento.
CREATE INDEX IF NOT EXISTS idx_whatsapp_processing_lease
ON whatsapp_inbound_events (processing_started_at)
WHERE status = 'processing';
