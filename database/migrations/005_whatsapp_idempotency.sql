-- Identificador del mensaje recibido desde Meta.
ALTER TABLE messages
ADD COLUMN meta_message_id VARCHAR(255);

-- Mensaje entrante que originó una respuesta automática.
ALTER TABLE messages
ADD COLUMN inbound_message_id BIGINT;

-- Evitar mensajes entrantes duplicados por organización.
CREATE UNIQUE INDEX uq_messages_meta_inbound
ON messages (tenant_id, meta_message_id)
WHERE direction = 'inbound'
  AND meta_message_id IS NOT NULL;

-- Evitar múltiples respuestas automáticas para el mismo mensaje.
CREATE UNIQUE INDEX uq_messages_outbound_source
ON messages (tenant_id, inbound_message_id)
WHERE direction = 'outbound'
  AND inbound_message_id IS NOT NULL;

-- Habilitar referencias compuestas por organización.
ALTER TABLE messages
ADD CONSTRAINT uq_messages_tenant_id
UNIQUE (tenant_id, id);

-- Garantizar que el mensaje relacionado pertenezca
-- a la misma organización.
ALTER TABLE messages
ADD CONSTRAINT fk_messages_inbound_source
FOREIGN KEY (tenant_id, inbound_message_id)
REFERENCES messages (tenant_id, id);
