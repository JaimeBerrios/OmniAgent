-- Identificador único del intento de procesamiento.
ALTER TABLE whatsapp_outbound_deliveries
ADD COLUMN IF NOT EXISTS claim_token UUID;

-- Fecha en que el trabajador reclamó la entrega.
ALTER TABLE whatsapp_outbound_deliveries
ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;

-- Evitar tokens duplicados entre entregas activas.
CREATE UNIQUE INDEX IF NOT EXISTS
    uq_whatsapp_outbound_claim_token
ON whatsapp_outbound_deliveries (claim_token)
WHERE claim_token IS NOT NULL;
