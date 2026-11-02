import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class N8NClientError(Exception):
    pass


def n8n_get(endpoint: str, params: dict | None = None) -> dict:
    base_url = os.environ["N8N_BASE_URL"].rstrip("/")
    api_key = os.environ["N8N_ADMIN_API_KEY"]

    url = f"{base_url}/api/v1/{endpoint.lstrip('/')}"

    if params:
        url += "?" + urlencode(params)

    request = Request(
        url,
        headers={
            "X-N8N-API-KEY": api_key,
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise N8NClientError(
            "No fue posible consultar la API administrativa de n8n"
        ) from exc


def list_workflows() -> dict:
    return n8n_get("workflows", {"limit": 100})


def list_executions(workflow_id: str, limit: int = 20) -> dict:
    return n8n_get(
        "executions",
        {"workflowId": workflow_id, "limit": limit},
    )
