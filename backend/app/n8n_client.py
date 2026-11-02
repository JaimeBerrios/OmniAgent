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


def n8n_control_workflow(workflow_id: str, action: str) -> dict:
    """Activa o desactiva un workflow mediante una credencial independiente."""
    if action not in ("activate", "deactivate"):
        raise ValueError("Acción de workflow no permitida")

    base_url = os.environ["N8N_BASE_URL"].rstrip("/")
    api_key = os.environ["N8N_CONTROL_API_KEY"]
    url = f"{base_url}/api/v1/workflows/{workflow_id}/{action}"

    request = Request(
        url,
        data=b"{}",
        method="POST",
        headers={
            "X-N8N-API-KEY": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            return json.load(response)
    except HTTPError as exc:
        raise N8NClientError(
            f"n8n rechazó la acción {action} con HTTP {exc.code}"
        ) from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise N8NClientError(
            f"No fue posible ejecutar la acción {action} en n8n"
        ) from exc


def get_workflow_state(workflow_id: str) -> dict:
    """Consulta el estado actual del workflow sin modificarlo."""
    workflow = n8n_get(f"workflows/{workflow_id}")

    return {
        "id": workflow.get("id"),
        "name": workflow.get("name"),
        "active": workflow.get("active"),
        "archived": workflow.get("isArchived"),
    }


def verify_workflow_action(workflow_id: str, action: str) -> dict:
    """Consulta si el estado actual coincide con la acción solicitada."""
    if action not in ("activate", "deactivate"):
        raise ValueError("Acción de workflow no permitida")

    workflow = get_workflow_state(workflow_id)

    expected_active = action == "activate"

    return {
        "workflow": workflow,
        "expected_active": expected_active,
        "matches_expected": workflow["active"] is expected_active,
    }
