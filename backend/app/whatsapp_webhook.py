import hashlib
import hmac
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import WhatsAppInboundEvent

router = APIRouter(prefix="/webhooks/whatsapp", tags=["WhatsApp"])

logger = logging.getLogger(__name__)

N8N_WEBHOOK_URL = "http://n8n:5678/webhook/omniagent-mensajes"


@router.get("")
def verify_webhook(
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
):
    verify_token = os.environ.get("META_VERIFY_TOKEN")

    if not verify_token:
        raise HTTPException(
            status_code=503,
            detail="Webhook no configurado",
        )

    if mode != "subscribe" or not hmac.compare_digest(
        token, verify_token
    ):
        raise HTTPException(
            status_code=403,
            detail="Verificación rechazada",
        )

    return PlainTextResponse(challenge)


def forward_to_n8n(sender_phone, message, meta_message_id):
    payload = {
        "cliente_id": sender_phone,
        "mensaje": message,
        "meta_message_id": meta_message_id,
    }

    request = urllib.request.Request(
        N8N_WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError("n8n no confirmó el procesamiento")


def process_message(db, message, phone_number_id):
    """Registrar el mensaje sin enviarlo directamente a n8n."""
    if not isinstance(message, dict):
        return "ignored"

    if message.get("type") != "text":
        return "ignored"

    meta_message_id = message.get("id")
    sender_phone = message.get("from")
    content = message.get("text", {}).get("body")

    if not all([
        isinstance(value, str) and value.strip()
        for value in (meta_message_id, sender_phone, content)
    ]):
        return "ignored"

    if (
        len(meta_message_id) > 255
        or len(sender_phone) > 50
        or len(content) > 4096
    ):
        return "ignored"

    result = db.execute(
        text("""
            INSERT INTO whatsapp_inbound_events (
                tenant_id,
                phone_number_id,
                meta_message_id,
                sender_phone,
                message_body,
                status,
                next_retry_at
            )
            VALUES (
                :tenant_id,
                :phone_number_id,
                :meta_message_id,
                :sender_phone,
                :message_body,
                'pending',
                NOW()
            )
            ON CONFLICT (phone_number_id, meta_message_id)
            DO NOTHING
            RETURNING id
        """),
        {
            "tenant_id": int(os.environ["WHATSAPP_TENANT_ID"]),
            "phone_number_id": phone_number_id,
            "meta_message_id": meta_message_id,
            "sender_phone": sender_phone,
            "message_body": content,
        },
    ).scalar_one_or_none()

    return "received" if result is not None else "duplicate"


@router.post("")
async def receive_webhook(request: Request):
    app_secret = os.environ.get("META_APP_SECRET")

    if not app_secret:
        raise HTTPException(
            status_code=503,
            detail="Webhook no configurado",
        )

    body = await request.body()
    signature = request.headers.get(
        "X-Hub-Signature-256", ""
    )

    expected = "sha256=" + hmac.new(
        app_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        raise HTTPException(
            status_code=403,
            detail="Firma inválida",
        )

    payload = json.loads(body)

    if payload.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}

    expected_phone_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]

    received = 0
    duplicates = 0
    ignored = 0

    try:
        with SessionLocal.begin() as db:
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    if change.get("field") != "messages":
                        continue

                    value = change.get("value", {})
                    phone_number_id = value.get(
                        "metadata", {}
                    ).get("phone_number_id")

                    if phone_number_id != expected_phone_id:
                        ignored += 1
                        continue

                    for message in value.get("messages", []):
                        result = process_message(
                            db, message, phone_number_id
                        )

                        if result == "received":
                            received += 1
                        elif result == "duplicate":
                            duplicates += 1
                        else:
                            ignored += 1

    except Exception:
        logger.exception("Error registrando eventos de WhatsApp")
        raise HTTPException(
            status_code=503,
            detail="Error registrando mensajes",
        )

    return {
        "status": "received",
        "queued": received,
        "duplicates": duplicates,
        "ignored": ignored,
    }
