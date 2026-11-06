import hashlib
import hmac
import json
import logging
import os

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from app.database import SessionLocal

router = APIRouter(
    prefix="/webhooks/messenger",
    tags=["Messenger"],
)

logger = logging.getLogger(__name__)


@router.get("")
def verify_webhook(
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
):
    expected = os.environ.get("MESSENGER_VERIFY_TOKEN")

    if not expected:
        raise HTTPException(503, "Webhook no configurado")

    if mode != "subscribe" or not hmac.compare_digest(
        token, expected
    ):
        raise HTTPException(403, "Verificación rechazada")

    return PlainTextResponse(challenge)


@router.post("")
async def receive_webhook(request: Request):
    secret = os.environ.get("META_APP_SECRET")

    if not secret:
        raise HTTPException(503, "Webhook no configurado")

    body = await request.body()
    signature = request.headers.get(
        "X-Hub-Signature-256", ""
    )

    expected = "sha256=" + hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        raise HTTPException(403, "Firma inválida")

    try:
        payload = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "JSON inválido")

    if not isinstance(payload, dict):
        raise HTTPException(400, "Payload inválido")

    if payload.get("object") != "page":
        return {"status": "ignored"}

    received = 0
    duplicates = 0
    ignored = 0

    try:
        with SessionLocal.begin() as db:
            for entry in payload.get("entry", []):
                if not isinstance(entry, dict):
                    ignored += 1
                    continue

                page_id = entry.get("id")

                if not isinstance(page_id, str):
                    ignored += 1
                    continue

                page = db.execute(
                    text("""
                        SELECT tenant_id
                        FROM messenger_pages
                        WHERE page_id = :page_id
                          AND is_active = TRUE
                    """),
                    {"page_id": page_id},
                ).scalar_one_or_none()

                if page is None:
                    ignored += 1
                    continue

                for event in entry.get("messaging", []):
                    if not isinstance(event, dict):
                        ignored += 1
                        continue

                    message = event.get("message", {})
                    sender = event.get("sender", {})

                    if not isinstance(message, dict) or not isinstance(sender, dict):
                        ignored += 1
                        continue

                    if message.get("is_echo"):
                        ignored += 1
                        continue

                    mid = message.get("mid")
                    psid = sender.get("id")
                    content = message.get("text")

                    if not all(
                        isinstance(v, str) and v.strip()
                        for v in (mid, psid, content)
                    ):
                        ignored += 1
                        continue

                    if (
                        len(mid) > 255
                        or len(psid) > 150
                        or len(content) > 4096
                    ):
                        ignored += 1
                        continue

                    result = db.execute(
                        text("""
                            INSERT INTO messenger_inbound_events (
                                tenant_id,
                                page_id,
                                sender_psid,
                                meta_message_id,
                                message_body,
                                status,
                                next_retry_at
                            )
                            VALUES (
                                :tenant_id,
                                :page_id,
                                :psid,
                                :mid,
                                :content,
                                'pending',
                                NOW()
                            )
                            ON CONFLICT (page_id, meta_message_id)
                            DO NOTHING
                            RETURNING id
                        """),
                        {
                            "tenant_id": page,
                            "page_id": page_id,
                            "psid": psid,
                            "mid": mid,
                            "content": content,
                        },
                    ).scalar_one_or_none()

                    if result is None:
                        duplicates += 1
                    else:
                        received += 1

    except Exception:
        logger.exception("Error registrando eventos de Messenger")
        raise HTTPException(
            503,
            "Error registrando mensajes",
        )

    return {
        "status": "received",
        "queued": received,
        "duplicates": duplicates,
        "ignored": ignored,
    }
