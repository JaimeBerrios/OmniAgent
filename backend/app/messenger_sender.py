import json
import os
import urllib.error
import urllib.request


GRAPH_API_VERSION = "v24.0"


class MessengerSendError(Exception):
    pass


class MessengerDeliveryUnknown(MessengerSendError):
    pass


def send_messenger_message(page_id: str, psid: str, content: str) -> str:
    if os.getenv("MESSENGER_OUTBOUND_ENABLED", "false").lower() != "true":
        raise MessengerSendError("Envío de Messenger desactivado")

    token = os.getenv("MESSENGER_PAGE_ACCESS_TOKEN")

    if not token:
        raise MessengerSendError("Token de Messenger no configurado")

    if not page_id.isascii() or not page_id.isdigit():
        raise MessengerSendError("Identificador de página inválido")

    if not psid.isascii() or not psid.isdigit():
        raise MessengerSendError("PSID inválido")

    if not content.strip():
        raise MessengerSendError("El mensaje está vacío")

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/messages"

    payload = {
        "recipient": {"id": psid},
        "messaging_type": "RESPONSE",
        "message": {"text": content},
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
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.load(response)

    except urllib.error.HTTPError as error:
        raise MessengerSendError(
            f"Meta rechazó el envío: HTTP {error.code}"
        ) from error

    except (urllib.error.URLError, TimeoutError) as error:
        raise MessengerDeliveryUnknown(
            "No fue posible confirmar la entrega con Meta"
        ) from error

    message_id = result.get("message_id")

    if not isinstance(message_id, str) or not message_id:
        raise MessengerDeliveryUnknown(
            "Meta no devolvió un identificador de mensaje"
        )

    return message_id
