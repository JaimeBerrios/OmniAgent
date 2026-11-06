import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("omniagent.messenger_worker")

POLL_INTERVAL = 2
LEASE_SECONDS = 300
MAX_RETRY_SECONDS = 300


def claim_event():
    with SessionLocal.begin() as db:
        event = db.execute(
            text("""
                SELECT id, tenant_id, page_id, sender_psid,
                       meta_message_id, message_body, attempts
                FROM messenger_inbound_events
                WHERE (
                    status IN ('pending', 'failed')
                    AND (
                        next_retry_at IS NULL
                        OR next_retry_at <= NOW()
                    )
                )
                OR (
                    status = 'processing'
                    AND processing_started_at
                        < NOW() - INTERVAL '300 seconds'
                )
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            """)
        ).mappings().first()

        if event is None:
            return None

        event = dict(event)
        token = uuid.uuid4()

        db.execute(
            text("""
                UPDATE messenger_inbound_events
                SET status = 'processing',
                    attempts = attempts + 1,
                    processing_started_at = NOW(),
                    claim_token = :token
                WHERE id = :id
            """),
            {"id": event["id"], "token": token},
        )

        event["claim_token"] = token
        return event



def fetch_profile_name(psid):
    token = os.environ.get("MESSENGER_PAGE_ACCESS_TOKEN")

    if not token:
        logger.warning("Token de Messenger no configurado")
        return None

    params = urllib.parse.urlencode({
        "fields": "name",
        "access_token": token,
    })

    url = (
        "https://graph.facebook.com/v24.0/"
        + urllib.parse.quote(psid, safe="")
        + "?"
        + params
    )

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.load(response)

        name = data.get("name")

        if isinstance(name, str):
            return name.strip()[:150] or None

    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        logger.warning(
            "No se pudo consultar el perfil de Messenger: %s",
            type(error).__name__,
        )

    return None

def process_event(event):
    tenant_id = event["tenant_id"]
    page_id = event["page_id"]
    psid = event["sender_psid"]

    external_id = f"fb:{page_id}:{psid}"

    if len(external_id) > 150:
        raise ValueError("Identificador de cliente demasiado largo")

    profile_name = fetch_profile_name(psid)

    with SessionLocal.begin() as db:
        current = db.execute(
            text("""
                SELECT id
                FROM messenger_inbound_events
                WHERE id = :id
                  AND status = 'processing'
                  AND claim_token = :token
                FOR UPDATE
            """),
            {"id": event["id"], "token": event["claim_token"]},
        ).first()

        if current is None:
            logger.warning("Evento %s ya no pertenece al worker", event["id"])
            return

        existing = db.execute(
            text("""
                SELECT id
                FROM messages
                WHERE tenant_id = :tenant_id
                  AND meta_message_id = :mid
                  AND direction = 'inbound'
            """),
            {"tenant_id": tenant_id, "mid": event["meta_message_id"]},
        ).scalar_one_or_none()

        if existing is None:
            customer_id = db.execute(
                text("""
                    INSERT INTO customers (tenant_id, external_id)
                    VALUES (:tenant_id, :external_id)
                    ON CONFLICT (tenant_id, external_id)
                    DO UPDATE SET external_id = EXCLUDED.external_id
                    RETURNING id
                """),
                {"tenant_id": tenant_id, "external_id": external_id},
            ).scalar_one()

            if profile_name:
                db.execute(
                    text("""
                        UPDATE customers
                        SET name = :name
                        WHERE tenant_id = :tenant_id
                          AND id = :customer_id
                          AND name IS NULL
                    """),
                    {
                        "name": profile_name,
                        "tenant_id": tenant_id,
                        "customer_id": customer_id,
                    },
                )

            conversation_id = db.execute(
                text("""
                    SELECT id
                    FROM conversations
                    WHERE tenant_id = :tenant_id
                      AND customer_id = :customer_id
                      AND channel = 'messenger'
                      AND status = 'open'
                    ORDER BY id DESC
                    LIMIT 1
                    FOR UPDATE
                """),
                {"tenant_id": tenant_id, "customer_id": customer_id},
            ).scalar_one_or_none()

            if conversation_id is None:
                conversation_id = db.execute(
                    text("""
                        INSERT INTO conversations
                            (tenant_id, customer_id, channel)
                        VALUES
                            (:tenant_id, :customer_id, 'messenger')
                        RETURNING id
                    """),
                    {"tenant_id": tenant_id, "customer_id": customer_id},
                ).scalar_one()

            db.execute(
                text("""
                    INSERT INTO messages
                        (tenant_id, conversation_id, direction,
                         content, meta_message_id)
                    VALUES
                        (:tenant_id, :conversation_id, 'inbound',
                         :content, :mid)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "tenant_id": tenant_id,
                    "conversation_id": conversation_id,
                    "content": event["message_body"],
                    "mid": event["meta_message_id"],
                },
            )

        db.execute(
            text("""
                UPDATE messenger_inbound_events
                SET status = 'processed',
                    processed_at = NOW(),
                    processing_started_at = NULL,
                    next_retry_at = NULL,
                    claim_token = NULL,
                    last_error = NULL
                WHERE id = :id
                  AND claim_token = :token
            """),
            {"id": event["id"], "token": event["claim_token"]},
        )


def fail_event(event, error):
    with SessionLocal.begin() as db:
        attempts = event["attempts"] + 1
        delay = min(2 ** min(attempts, 8), MAX_RETRY_SECONDS)

        db.execute(
            text("""
                UPDATE messenger_inbound_events
                SET status = 'failed',
                    processing_started_at = NULL,
                    claim_token = NULL,
                    next_retry_at = NOW() + (:delay * INTERVAL '1 second'),
                    last_error = :error
                WHERE id = :id
                  AND claim_token = :token
                  AND status = 'processing'
            """),
            {
                "id": event["id"],
                "token": event["claim_token"],
                "delay": delay,
                "error": str(error)[:1000],
            },
        )


def main():
    logger.info("Worker de Facebook Messenger iniciado")

    while True:
        try:
            event = claim_event()

            if event is None:
                time.sleep(POLL_INTERVAL)
                continue

            try:
                process_event(event)
                logger.info("Evento %s procesado", event["id"])
            except Exception as error:
                logger.exception("Error procesando evento %s", event["id"])
                fail_event(event, error)

        except Exception:
            logger.exception("Error en el ciclo del worker")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
