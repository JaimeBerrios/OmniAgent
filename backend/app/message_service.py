"""Persist a reply and its channel outbox in the caller's transaction."""
from fastapi import HTTPException
from sqlalchemy import select
from .models import Customer, Message, MessengerPage, MessengerOutboundDelivery, WhatsAppOutboundDelivery


def enqueue_reply(db, conversation, content, *, idempotency_key=None, inbound_message_id=None):
    # Serialize writers for this conversation, including retries with the same key.
    from .models import Conversation
    conversation = db.scalar(select(Conversation).where(
        Conversation.id == conversation.id, Conversation.tenant_id == conversation.tenant_id
    ).with_for_update().execution_options(populate_existing=True))
    if idempotency_key:
        existing = db.scalar(select(Message).where(
            Message.tenant_id == conversation.tenant_id,
            Message.conversation_id == conversation.id,
            Message.idempotency_key == idempotency_key))
        if existing:
            if existing.direction != 'outbound' or existing.content != content:
                raise HTTPException(409, 'La clave ya identifica otro mensaje')
            return existing
    if conversation.channel not in ('whatsapp', 'messenger', 'website'):
        raise HTTPException(422, 'El canal no admite entrega de respuestas')
    customer = db.scalar(select(Customer).where(Customer.id == conversation.customer_id,
                                               Customer.tenant_id == conversation.tenant_id))
    if customer is None:
        raise HTTPException(404, 'Cliente no encontrado')
    delivery = None
    if conversation.channel == 'whatsapp':
        phone = customer.external_id
        if not (phone.isascii() and phone.isdigit() and 8 <= len(phone) <= 15):
            raise HTTPException(422, 'Destinatario de WhatsApp inválido')
        delivery = WhatsAppOutboundDelivery(tenant_id=conversation.tenant_id, recipient_phone=phone)
    elif conversation.channel == 'messenger':
        parts = customer.external_id.split(':')
        if len(parts) != 3 or parts[0] != 'fb' or not all(x.isascii() and x.isdigit() for x in parts[1:]):
            raise HTTPException(422, 'Identificador de Messenger inválido')
        page = db.scalar(select(MessengerPage).where(MessengerPage.tenant_id == conversation.tenant_id,
                MessengerPage.page_id == parts[1], MessengerPage.is_active.is_(True)))
        if page is None:
            raise HTTPException(422, 'Página de Messenger no activa o no autorizada')
        delivery = MessengerOutboundDelivery(tenant_id=conversation.tenant_id,
                                             page_id=parts[1], recipient_psid=parts[2])
    message = Message(tenant_id=conversation.tenant_id, conversation_id=conversation.id,
                      direction='outbound', content=content, idempotency_key=idempotency_key,
                      inbound_message_id=inbound_message_id)
    db.add(message)
    db.flush()
    if delivery is not None:
        delivery.message_id = message.id
        delivery.status = 'pending'
        db.add(delivery)
        db.flush()
    return message
