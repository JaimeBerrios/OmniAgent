import json
import os
import urllib.error
import urllib.request


class WhatsAppSendError(Exception):
    def __init__(self, message: str, outcome: str = "unknown"):
        super().__init__(message)
        self.outcome = outcome


def send_whatsapp_message(recipient: str, message: str) -> str:
    token = os.environ["META_ACCESS_TOKEN"]
    phone_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]

    if not recipient.isdigit() or not message.strip():
        raise ValueError("Destinatario o mensaje inválido")

    url = f"https://graph.facebook.com/v26.0/{phone_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "text",
        "text": {"body": message},
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)

        return result["messages"][0]["id"]

    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8")
        raise WhatsAppSendError(
            f"Meta HTTP {error.code}: {details}",
            outcome="rejected" if 400 <= error.code < 500
            and error.code not in (408, 429) else "unknown",
        ) from error

    except (urllib.error.URLError, TimeoutError) as error:
        raise WhatsAppSendError(
            f"Error de comunicación con Meta: {error}"
        ) from error
