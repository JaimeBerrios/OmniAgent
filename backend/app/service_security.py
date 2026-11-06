
import os
import secrets

from fastapi import Header, HTTPException, status


def require_service_key(
    x_service_key: str | None = Header(default=None),
) -> int:
    expected_key = os.environ.get("N8N_API_KEY")
    if not expected_key:
        raise HTTPException(503, "Servicio no configurado")

    if (
        not x_service_key
        or not x_service_key.isascii()
        or not secrets.compare_digest(
            x_service_key,
            expected_key,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credencial de servicio inválida",
        )

    tenant_id = int(os.environ["N8N_TENANT_ID"])

    return tenant_id
