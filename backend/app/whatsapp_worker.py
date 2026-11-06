import uuid
import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from app.database import SessionLocal
from app.models import WhatsAppInboundEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("omniagent.whatsapp_worker")

N8N_URL = os.environ.get("N8N_WEBHOOK_URL", "http://n8n:5678/webhook/omniagent-mensajes")
TENANT_ID = int(os.environ["WHATSAPP_TENANT_ID"])
PHONE_NUMBER_ID = os.environ["WHATSAPP_PHONE_NUMBER_ID"]

POLL_INTERVAL = 2
LEASE_SECONDS = 300
MAX_RETRY_SECONDS = 300


def claim_event():
    now = datetime.now(timezone.utc)

    with SessionLocal.begin() as db:
        event = db.scalar(
            select(WhatsAppInboundEvent)
            .where(
                WhatsAppInboundEvent.tenant_id == TENANT_ID,
                WhatsAppInboundEvent.phone_number_id == PHONE_NUMBER_ID,
                (
                    (
                        WhatsAppInboundEvent.status.in_(
                            ["pending", "failed"]
                        )
                        & (
                            (WhatsAppInboundEvent.next_retry_at <= now)
                            | (
                                WhatsAppInboundEvent.next_retry_at.is_(None)
                            )
                        )
                    )
                    |
                    (
                        (WhatsAppInboundEvent.status == "processing")
                        & (
                            WhatsAppInboundEvent.processing_started_at
                            < now - timedelta(seconds=LEASE_SECONDS)
                        )
                    )
                ),
            )
            .order_by(WhatsAppInboundEvent.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )

        if event is None:
            return None

        event.status = "processing"
        event.attempts += 1
        event.processing_started_at = now
        event.claim_token = uuid.uuid4()

        db.flush()

        return {
            "id": event.id,
            "sender_phone": event.sender_phone,
            "message_body": event.message_body,
            "meta_message_id": event.meta_message_id,
            "attempts": event.attempts,
            "processing_started_at": now,
            "claim_token": event.claim_token,
        }


def send_to_n8n(event):
    payload = {
        "cliente_id": event["sender_phone"],
        "mensaje": event["message_body"],
        "meta_message_id": event["meta_message_id"],
    }

    request = urllib.request.Request(
        N8N_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Webhook-Key": os.environ["N8N_WEBHOOK_KEY"]},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError("n8n no confirmó el procesamiento")


def finish_event(event, success):
    with SessionLocal.begin() as db:
        current = db.scalar(
            select(WhatsAppInboundEvent)
            .where(
                WhatsAppInboundEvent.id == event["id"],
                WhatsAppInboundEvent.tenant_id == TENANT_ID,
                WhatsAppInboundEvent.status == "processing",
                WhatsAppInboundEvent.claim_token
                == event["claim_token"],
            )
            .with_for_update()
        )

        if current is None:
            logger.warning(
                "Resultado obsoleto descartado para evento %s",
                event["id"],
            )
            return

        current.processing_started_at = None
        current.claim_token = None

        if success:
            current.status = "processed"
            current.processed_at = datetime.now(timezone.utc)
            current.next_retry_at = None
            current.last_error = None
        else:
            current.status = "failed"
            delay = min(
                2 ** min(current.attempts, 8),
                MAX_RETRY_SECONDS,
            )
            current.next_retry_at = (
                datetime.now(timezone.utc)
                + timedelta(seconds=delay)
            )
            current.last_error = "Error de entrega a n8n"


def main():
    logger.info("Worker de WhatsApp iniciado version=%s", os.environ.get("APP_VERSION", "dev"))

    while True:
        try:
            event = claim_event()

            if event is None:
                time.sleep(POLL_INTERVAL)
                continue

            try:
                if not event["message_body"]:
                    raise ValueError("Evento sin contenido")

                send_to_n8n(event)
                finish_event(event, True)

                logger.info(
                    "Evento %s procesado",
                    event["id"],
                )

            except Exception:
                logger.exception(
                    "Error procesando evento %s",
                    event["id"],
                )
                finish_event(event, False)

        except Exception:
            logger.exception("Error en el ciclo del worker")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
