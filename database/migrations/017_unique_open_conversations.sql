-- Impide múltiples conversaciones abiertas
-- para un mismo cliente, canal y tenant.

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_conversations_open_customer_channel
ON conversations (tenant_id, customer_id, channel)
WHERE status = 'open';
