import logging
import os
import time
import uuid

from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update

from app.database import SessionLocal
from app.models import (
    Conversation, Customer, Message,
    MessengerPage, MessengerOutboundDelivery,
)
from app.messenger_sender import (
    MessengerSendError,
    MessengerDeliveryUnknown,
    send_messenger_message,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("omniagent.messenger_outbound_worker")

POLL_INTERVAL = 2
OUTBOUND_ENABLED = (
    os.getenv("MESSENGER_OUTBOUND_ENABLED", "false").lower()
    == "true"
)


def claim_delivery():
    with SessionLocal.begin() as db:
        delivery = db.scalar(
            select(MessengerOutboundDelivery)
            .where(
                MessengerOutboundDelivery.status == "pending"
            )
            .order_by(
                MessengerOutboundDelivery.created_at,
                MessengerOutboundDelivery.id,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )

        if delivery is None:
            return None

        message = db.scalar(
            select(Message).where(
                Message.id == delivery.message_id,
                Message.tenant_id == delivery.tenant_id,
                Message.direction == "outbound",
            )
        )

        if message is None:
            delivery.status = "failed"
            delivery.last_error = "Mensaje saliente inexistente"
            return None

        conversation = db.scalar(
            select(Conversation).where(
                Conversation.id == message.conversation_id,
                Conversation.tenant_id == delivery.tenant_id,
                Conversation.channel == "messenger",
            )
        )

        page = db.scalar(
            select(MessengerPage).where(
                MessengerPage.tenant_id == delivery.tenant_id,
                MessengerPage.page_id == delivery.page_id,
                MessengerPage.is_active.is_(True),
            )
        )

        customer = None
        if conversation is not None:
            customer = db.scalar(
                select(Customer).where(
                    Customer.id == conversation.customer_id,
                    Customer.tenant_id == delivery.tenant_id,
                )
            )

        expected_external_id = (
            f"fb:{delivery.page_id}:{delivery.recipient_psid}"
        )

        if (
            conversation is None
            or page is None
            or customer is None
            or customer.external_id != expected_external_id
            or not delivery.page_id.isascii()
            or not delivery.page_id.isdigit()
            or not delivery.recipient_psid.isascii()
            or not delivery.recipient_psid.isdigit()
        ):
            delivery.status = "failed"
            delivery.last_error = (
                "Página, organización o destinatario no válido"
            )
            return None

        token = uuid.uuid4()

        delivery.status = "sending"
        delivery.attempts += 1
        delivery.claim_token = token
        delivery.claimed_at = datetime.now(timezone.utc)

        return {
            "id": delivery.id,
            "message_id": delivery.message_id,
            "tenant_id": delivery.tenant_id,
            "page_id": delivery.page_id,
            "psid": delivery.recipient_psid,
            "content": message.content,
            "token": token,
        }


def finish_delivery(delivery_id, token, status, message_id=None, error=None):
    if status not in ("sent", "failed", "unknown"):
        raise ValueError("Estado de entrega inválido")

    with SessionLocal.begin() as db:
        delivery = db.scalar(
            select(MessengerOutboundDelivery)
            .where(
                MessengerOutboundDelivery.id == delivery_id,
                MessengerOutboundDelivery.status == "sending",
                MessengerOutboundDelivery.claim_token == token,
            )
            .with_for_update()
        )

        if delivery is None:
            return False

        delivery.status = status
        delivery.meta_message_id = message_id
        delivery.last_error = error
        delivery.claim_token = None
        delivery.claimed_at = None
        delivery.updated_at = datetime.now(timezone.utc)

        return True


def recover_interrupted():
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)

    with SessionLocal.begin() as db:
        result = db.execute(
            update(MessengerOutboundDelivery)
            .where(
                MessengerOutboundDelivery.status == "sending",
                MessengerOutboundDelivery.claimed_at < cutoff,
            )
            .values(
                status="unknown",
                claim_token=None,
                claimed_at=None,
                last_error="Entrega interrumpida; resultado no confirmado",
                updated_at=datetime.now(timezone.utc),
            )
            .returning(MessengerOutboundDelivery.id)
        )

        return result.scalars().all()



def is_customer_service_window_open(db, tenant_id, conversation_id):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    last_inbound = db.scalar(
        select(Message.created_at)
        .where(
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation_id,
            Message.direction == "inbound",
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )

    return (
        last_inbound is not None
        and cutoff <= last_inbound <= now
    )


def is_delivery_authorized(db, delivery):
    return db.scalar(
        select(MessengerOutboundDelivery.id)
        .where(
            MessengerOutboundDelivery.id == delivery["id"],
            MessengerOutboundDelivery.message_id == delivery["message_id"],
            MessengerOutboundDelivery.tenant_id == delivery["tenant_id"],
            MessengerOutboundDelivery.page_id == delivery["page_id"],
            MessengerOutboundDelivery.recipient_psid == delivery["psid"],
            MessengerOutboundDelivery.status == "sending",
            MessengerOutboundDelivery.claim_token == delivery["token"],
        )
        .limit(1)
    ) is not None

def process_delivery(delivery):
    with SessionLocal() as db:
        message = db.scalar(
            select(Message).where(
                Message.id == delivery["message_id"],
                Message.tenant_id == delivery["tenant_id"],
                Message.direction == "outbound",
            )
        )

        conversation = None
        customer = None

        if message is not None:
            conversation = db.scalar(
                select(Conversation).where(
                    Conversation.id == message.conversation_id,
                    Conversation.tenant_id == delivery["tenant_id"],
                    Conversation.channel == "messenger",
                )
            )

        if conversation is not None:
            customer = db.scalar(
                select(Customer).where(
                    Customer.id == conversation.customer_id,
                    Customer.tenant_id == delivery["tenant_id"],
                )
            )

        page = db.scalar(
            select(MessengerPage).where(
                MessengerPage.tenant_id == delivery["tenant_id"],
                MessengerPage.page_id == delivery["page_id"],
                MessengerPage.is_active.is_(True),
            )
        )

        expected_external_id = (
            f'fb:{delivery["page_id"]}:{delivery["psid"]}'
        )

        valid_recipient = (
            conversation is not None
            and customer is not None
            and page is not None
            and customer.external_id == expected_external_id
        )

        window_open = (
            valid_recipient
            and is_customer_service_window_open(
                db,
                delivery["tenant_id"],
                message.conversation_id,
            )
        )

        authorized = is_delivery_authorized(db, delivery)

    if not authorized:
        logger.warning(
            "Entrega %s sin autorización vigente",
            delivery["id"],
        )
        return

    if not valid_recipient:
        finish_delivery(
            delivery["id"],
            delivery["token"],
            "failed",
            error="Página o destinatario no válido antes del envío",
        )
        return

    if not window_open:
        finish_delivery(
            delivery["id"],
            delivery["token"],
            "failed",
            error="Ventana de atención de 24 horas cerrada",
        )
        return

    try:
        message_id = send_messenger_message(
            delivery["page_id"],
            delivery["psid"],
            delivery["content"],
        )

    except MessengerSendError as error:
        status = (
            "unknown"
            if isinstance(error, MessengerDeliveryUnknown)
            else "failed"
        )
        finish_delivery(
            delivery["id"],
            delivery["token"],
            status,
            error=str(error),
        )
        logger.warning(
            "Entrega %s sin confirmación: %s",
            delivery["id"],
            error,
        )
        return

    except Exception:
        logger.exception("Resultado incierto para entrega %s", delivery["id"])
        finish_delivery(delivery["id"], delivery["token"], "unknown", error="Error inesperado durante el envío")
        return

    finish_delivery(
        delivery["id"],
        delivery["token"],
        "sent",
        message_id=message_id,
    )

    logger.info("Entrega %s enviada", delivery["id"])


def main():
    logger.info("version=%s", os.environ.get("APP_VERSION", "dev"))
    logger.info("Worker saliente de Messenger iniciado")

    while True:
        if not OUTBOUND_ENABLED:
            logger.info("Envío saliente desactivado")
            time.sleep(60)
            continue

        try:
            recovered = recover_interrupted()

            if recovered:
                logger.warning(
                    "Entregas con resultado desconocido: %s",
                    recovered,
                )

            delivery = claim_delivery()

            if delivery:
                process_delivery(delivery)
            else:
                time.sleep(POLL_INTERVAL)
        except Exception:
            logger.exception("Error en el ciclo del worker saliente")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
