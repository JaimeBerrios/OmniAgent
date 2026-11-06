import uuid
import logging
import os
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.database import SessionLocal
from app.models import Message, WhatsAppOutboundDelivery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("omniagent.whatsapp_outbound_worker")

TENANT_ID = int(os.environ["WHATSAPP_TENANT_ID"])
OUTBOUND_ENABLED = (
    os.environ.get("WHATSAPP_OUTBOUND_ENABLED", "false").lower()
    == "true"
)

from app.whatsapp_sender import WhatsAppSendError

POLL_INTERVAL = 2


def get_pending_deliveries():
    with SessionLocal() as db:
        deliveries = db.scalars(
            select(WhatsAppOutboundDelivery)
            .where(
                WhatsAppOutboundDelivery.tenant_id == TENANT_ID,
                WhatsAppOutboundDelivery.status == "pending",
            )
            .order_by(WhatsAppOutboundDelivery.created_at)
            .limit(10)
        ).all()

        return [
            {
                "id": delivery.id,
                "message_id": delivery.message_id,
                "recipient_phone": delivery.recipient_phone,
            }
            for delivery in deliveries
        ]



def claim_delivery():
    with SessionLocal.begin() as db:
        delivery = db.scalar(
            select(WhatsAppOutboundDelivery)
            .where(
                WhatsAppOutboundDelivery.tenant_id == TENANT_ID,
                WhatsAppOutboundDelivery.status == "pending",
            )
            .order_by(
                WhatsAppOutboundDelivery.created_at,
                WhatsAppOutboundDelivery.id,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )

        if delivery is None:
            return None

        delivery.updated_at = datetime.now(timezone.utc)
        delivery.status = "sending"
        delivery.attempts += 1
        delivery.claim_token = uuid.uuid4()
        delivery.claimed_at = datetime.now(timezone.utc)
        db.flush()

        return {
            "id": delivery.id,
            "message_id": delivery.message_id,
            "recipient_phone": delivery.recipient_phone,
            "attempts": delivery.attempts,
            "claim_token": delivery.claim_token,
        }


def recover_interrupted_deliveries():
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)

    with SessionLocal.begin() as db:
        result = db.execute(
            update(WhatsAppOutboundDelivery)
            .where(
                WhatsAppOutboundDelivery.tenant_id == TENANT_ID,
                WhatsAppOutboundDelivery.status == "sending",
                WhatsAppOutboundDelivery.claimed_at < cutoff,
            )
            .values(
                status="unknown",
                claim_token=None,
                claimed_at=None,
                last_error=(
                    "Tiempo de envío excedido; "
                    "resultado no confirmado"
                ),
            )
            .returning(WhatsAppOutboundDelivery.id)
        )

        recovered = result.scalars().all()

    return recovered


def recovery_cycle():
    recovered = recover_interrupted_deliveries()

    if recovered:
        logger.warning(
            "Entregas interrumpidas marcadas como unknown: %s",
            recovered,
        )

    return recovered


def finish_delivery(
    delivery_id,
    outcome,
    claim_token,
    meta_message_id=None,
    error=None,
):
    if not isinstance(claim_token, uuid.UUID):
        raise ValueError("claim_token debe ser un UUID válido")

    if outcome not in ("sent", "failed", "unknown"):
        raise ValueError("Resultado de entrega inválido")

    if outcome == "sent" and not meta_message_id:
        raise ValueError("El envío exitoso requiere wamid")

    if outcome != "sent" and meta_message_id:
        raise ValueError("wamid incompatible con el resultado")

    with SessionLocal.begin() as db:
        delivery = db.scalar(
            select(WhatsAppOutboundDelivery)
            .where(
                WhatsAppOutboundDelivery.id == delivery_id,
                WhatsAppOutboundDelivery.tenant_id == TENANT_ID,
                WhatsAppOutboundDelivery.status == "sending",
                WhatsAppOutboundDelivery.claim_token == claim_token,
            )
            .with_for_update()
        )

        if delivery is None:
            return False

        delivery.updated_at = datetime.now(timezone.utc)
        delivery.status = outcome
        delivery.meta_message_id = meta_message_id
        delivery.last_error = error
        delivery.claim_token = None
        delivery.claimed_at = None
        db.flush()

        return True



def is_customer_service_window_open(db, conversation_id):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    last_inbound = db.scalar(
        select(Message.created_at)
        .where(
            Message.tenant_id == TENANT_ID,
            Message.conversation_id == conversation_id,
            Message.direction == "inbound",
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )

    if last_inbound is None:
        return False

    return cutoff <= last_inbound <= datetime.now(timezone.utc)


def process_delivery(delivery, sender):
    delivery_id = delivery["id"]
    claim_token = delivery["claim_token"]

    with SessionLocal() as db:
        message = db.scalar(
            select(Message).where(
                Message.id == delivery["message_id"],
                Message.tenant_id == TENANT_ID,
                Message.direction == "outbound",
            )
        )

        if message is None:
            return finish_delivery(
                delivery_id,
                "failed",
                claim_token,
                error="Mensaje saliente no encontrado",
            )

        content = message.content

        window_open = is_customer_service_window_open(
            db,
            message.conversation_id,
        )

    if not window_open:
        logger.warning(
            "Ventana de 24 horas cerrada para entrega %s",
            delivery_id,
        )

        return finish_delivery(
            delivery_id,
            "failed",
            claim_token,
            error=(
                "Ventana de atención de WhatsApp cerrada; "
                "se requiere una plantilla aprobada"
            ),
        )

    try:
        wamid = sender(
            delivery["recipient_phone"],
            content,
        )

        return finish_delivery(
            delivery_id,
            "sent",
            claim_token,
            meta_message_id=wamid,
        )

    except WhatsAppSendError as exc:
        outcome = (
            "failed" if exc.outcome == "rejected"
            else "unknown"
        )

        return finish_delivery(
            delivery_id,
            outcome,
            claim_token,
            error=str(exc),
        )

    except Exception:
        logger.exception(
            "Resultado incierto para entrega %s",
            delivery_id,
        )

        return finish_delivery(
            delivery_id,
            "unknown",
            claim_token,
            error="Error inesperado durante el envío",
        )


def processing_cycle(sender):
    recovery_cycle()

    delivery = claim_delivery()

    if delivery is None:
        return None

    logger.info(
        "Procesando entrega %s (intento %s)",
        delivery["id"],
        delivery["attempts"],
    )

    result = process_delivery(delivery, sender)

    if not result:
        logger.warning(
            "No se pudo finalizar la entrega %s",
            delivery["id"],
        )

    return {
        "delivery_id": delivery["id"],
        "finalized": result,
    }


def main():
    logger.info("version=%s", os.environ.get("APP_VERSION", "dev"))
    logger.info("Trabajador de WhatsApp saliente iniciado")

    if not OUTBOUND_ENABLED:
        logger.warning(
            "Envíos reales desactivados. "
            "WHATSAPP_OUTBOUND_ENABLED=false"
        )
        while True:
            time.sleep(60)

    from app.whatsapp_sender import send_whatsapp_message

    logger.info(
        "Procesamiento continuo habilitado para tenant %s",
        TENANT_ID,
    )

    while True:
        try:
            processing_cycle(send_whatsapp_message)
        except Exception:
            logger.exception(
                "Error inesperado en el ciclo de procesamiento"
            )

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
