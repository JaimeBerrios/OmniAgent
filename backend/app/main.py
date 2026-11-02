from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .database import SessionLocal, engine, get_db
from .models import AutomationAudit, Conversation, Customer, Membership, Message, Tenant, User
from .service_security import require_service_key
from .schemas import (
    ConversationCreate,
    ConversationStatusUpdate,
    ConversationResponse,
    ConversationListResponse,
    CustomerCreate,
    CustomerResponse,
    LoginRequest,
    TokenResponse,
    MessageCreate,
    MessageResponse,
    ServiceMessageCreate,
    ServiceMessageResponse,
    ServiceOutboundMessageCreate,
    ServiceOutboundMessageResponse,
)
from .security import (
    create_access_token,
    get_current_user,
    require_tenant_membership,
    verify_password,
)

app = FastAPI(
    title="OmniAgent API",
    description="API de gestión omnicanal multi-tenant",
    version="1.0.0",
)


# ----------------------------------------
# GENERAL
# ----------------------------------------

@app.get("/")
def root():
    return {
        "application": "OmniAgent",
        "status": "running",
    }


@app.get("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected",
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible",
        )




# ----------------------------------------
# ESTADÍSTICAS DEL DASHBOARD
# ----------------------------------------

@app.get("/tenants/{tenant_id}/stats")
def get_tenant_stats(
    tenant_id: int,
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    tenant = membership.tenant_id

    customers = db.scalar(
        select(func.count(Customer.id))
        .where(Customer.tenant_id == tenant)
    )

    conversations = db.scalar(
        select(func.count(Conversation.id))
        .where(Conversation.tenant_id == tenant)
    )

    open_conversations = db.scalar(
        select(func.count(Conversation.id))
        .where(
            Conversation.tenant_id == tenant,
            Conversation.status == "open",
        )
    )

    inbound_messages = db.scalar(
        select(func.count(Message.id))
        .where(
            Message.tenant_id == tenant,
            Message.direction == "inbound",
        )
    )

    outbound_messages = db.scalar(
        select(func.count(Message.id))
        .where(
            Message.tenant_id == tenant,
            Message.direction == "outbound",
        )
    )

    return {
        "customers": customers,
        "conversations": conversations,
        "open_conversations": open_conversations,
        "inbound_messages": inbound_messages,
        "outbound_messages": outbound_messages,
    }


@app.get("/tenants/{tenant_id}/stats/activity")
def get_tenant_activity(
    tenant_id: int,
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=6)
    start = datetime.combine(
        start_date,
        datetime.min.time(),
        tzinfo=timezone.utc,
    )

    rows = db.execute(
        select(
            func.date(Message.created_at).label("day"),
            Message.direction,
            func.count(Message.id),
        )
        .where(
            Message.tenant_id == membership.tenant_id,
            Message.created_at >= start,
        )
        .group_by(
            func.date(Message.created_at),
            Message.direction,
        )
    ).all()

    activity = {
        (str(day), direction): count
        for day, direction, count in rows
    }

    return [
        {
            "date": day.isoformat(),
            "inbound": activity.get((day.isoformat(), "inbound"), 0),
            "outbound": activity.get((day.isoformat(), "outbound"), 0),
        }
        for day in (
            start_date + timedelta(days=offset)
            for offset in range(7)
        )
    ]


# ----------------------------------------
# AUTENTICACIÓN
# ----------------------------------------

@app.post(
    "/auth/login",
    response_model=TokenResponse,
)
def login(
    credentials: LoginRequest,
    db: Session = Depends(get_db),
):
    email = credentials.email.strip().lower()

    user = db.scalar(
        select(User).where(User.email == email)
    )

    if (
        user is None
        or not user.is_active
        or not verify_password(
            credentials.password,
            user.password_hash,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Credenciales inválidas",
        )

    return TokenResponse(
        access_token=create_access_token(user.id),
    )


@app.get("/auth/me")
def get_profile(
    current_user: User = Depends(get_current_user),
):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "is_active": current_user.is_active,
    }


# ----------------------------------------
# ORGANIZACIONES
# ----------------------------------------

@app.get("/tenants/{tenant_id}/me")
def get_tenant_profile(
    tenant_id: int,
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    tenant = db.get(Tenant, membership.tenant_id)

    if tenant is None:
        raise HTTPException(
            status_code=404,
            detail="Organización no encontrada",
        )

    return {
        "tenant_id": tenant.id,
        "organization": tenant.name,
        "role": membership.role,
    }


# ----------------------------------------
# CLIENTES
# ----------------------------------------

@app.get(
    "/tenants/{tenant_id}/customers",
    response_model=list[CustomerResponse],
)
def list_customers(
    tenant_id: int,
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    customers = db.scalars(
        select(Customer)
        .where(Customer.tenant_id == membership.tenant_id)
        .order_by(Customer.id)
    ).all()

    return customers


@app.post(
    "/tenants/{tenant_id}/customers",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    tenant_id: int,
    customer_data: CustomerCreate,
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    if membership.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="No tienes permisos para registrar clientes",
        )

    customer = Customer(
        tenant_id=membership.tenant_id,
        external_id=customer_data.external_id,
        name=customer_data.name,
    )

    try:
        db.add(customer)
        db.commit()
        db.refresh(customer)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "Ya existe un cliente con ese "
                "identificador en la organización"
            ),
        )

    return customer


# ----------------------------------------
# CONVERSACIONES
# ----------------------------------------
@app.get(
    "/tenants/{tenant_id}/conversations",
    response_model=list[ConversationListResponse],
)
def list_conversations(
    tenant_id: int,
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    conversations = db.execute(
        select(Conversation, Customer)
        .join(
            Customer,
            (Customer.id == Conversation.customer_id)
            & (Customer.tenant_id == Conversation.tenant_id),
        )
        .where(Conversation.tenant_id == membership.tenant_id)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
    ).all()

    result = []

    for conversation, customer in conversations:
        last_message = db.scalar(
            select(Message)
            .where(
                Message.tenant_id == membership.tenant_id,
                Message.conversation_id == conversation.id,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )

        result.append(
            ConversationListResponse(
                id=conversation.id,
                tenant_id=conversation.tenant_id,
                customer_id=conversation.customer_id,
                channel=conversation.channel,
                status=conversation.status,
                created_at=conversation.created_at,
                customer_name=customer.name,
                customer_external_id=customer.external_id,
                last_message=last_message.content if last_message else None,
                last_message_at=last_message.created_at if last_message else None,
            )
        )

    return result

@app.post(
    "/tenants/{tenant_id}/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    tenant_id: int,
    conversation_data: ConversationCreate,
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    customer = db.scalar(
        select(Customer).where(
            Customer.id == conversation_data.customer_id,
            Customer.tenant_id == membership.tenant_id,
        )
    )

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Cliente no encontrado en esta organización",
        )

    conversation = Conversation(
        tenant_id=membership.tenant_id,
        customer_id=customer.id,
        channel=conversation_data.channel,
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return conversation


@app.patch(
    "/tenants/{tenant_id}/conversations/{conversation_id}",
    response_model=ConversationResponse,
)
def update_conversation_status(
    tenant_id: int,
    conversation_id: int,
    data: ConversationStatusUpdate,
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == membership.tenant_id,
        )
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversación no encontrada en esta organización",
        )

    conversation.status = data.status
    db.commit()
    db.refresh(conversation)

    return conversation


# ----------------------------------------
# MENSAJES
# ----------------------------------------

@app.post(
    "/tenants/{tenant_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_message(
    tenant_id: int,
    message_data: MessageCreate,
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == message_data.conversation_id,
            Conversation.tenant_id == membership.tenant_id,
        )
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversación no encontrada en esta organización",
        )

    message = Message(
        tenant_id=membership.tenant_id,
        conversation_id=conversation.id,
        direction=message_data.direction,
        content=message_data.content,
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return message



@app.get(
    "/tenants/{tenant_id}/messages/recent",
    response_model=list[MessageResponse],
)
def list_recent_messages(
    tenant_id: int,
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(Message)
        .where(Message.tenant_id == membership.tenant_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(10)
    ).all()


@app.get(
    "/tenants/{tenant_id}/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
def list_conversation_messages(
    tenant_id: int,
    conversation_id: int,
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.tenant_id == membership.tenant_id,
        )
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversación no encontrada en esta organización",
        )

    messages = db.scalars(
        select(Message)
        .where(
            Message.tenant_id == membership.tenant_id,
            Message.conversation_id == conversation.id,
        )
        .order_by(Message.created_at, Message.id)
    ).all()

    return messages


@app.post(
    "/internal/messages/inbound",
    response_model=ServiceMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def receive_internal_message(
    message_data: ServiceMessageCreate,
    tenant_id: int = Depends(require_service_key),
    db: Session = Depends(get_db),
):
    customer = db.scalar(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.external_id == message_data.cliente_id,
        )
    )

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Cliente no encontrado en la organización autorizada",
        )

    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.customer_id == customer.id,
            Conversation.channel == "whatsapp",
            Conversation.status == "open",
        )
        .order_by(Conversation.id.desc())
        .limit(1)
    )

    if conversation is None:
        conversation = Conversation(
            tenant_id=tenant_id,
            customer_id=customer.id,
            channel="whatsapp",
        )
        db.add(conversation)
        db.flush()

    message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="inbound",
        content=message_data.mensaje,
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return ServiceMessageResponse(
        tenant_id=tenant_id,
        customer_id=customer.id,
        conversation_id=conversation.id,
        message_id=message.id,
        status="received",
    )


@app.post(
    "/internal/messages/outbound",
    response_model=ServiceOutboundMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def receive_outbound_message(
    message_data: ServiceOutboundMessageCreate,
    tenant_id: int = Depends(require_service_key),
    db: Session = Depends(get_db),
):
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == message_data.conversation_id,
            Conversation.tenant_id == tenant_id,
        )
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversación no encontrada en la organización autorizada",
        )

    message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="outbound",
        content=message_data.respuesta,
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return ServiceOutboundMessageResponse(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        message_id=message.id,
        direction="outbound",
        status="recorded",
    )


@app.get("/tenants/{tenant_id}/automations/status")
def get_automation_status(
    tenant_id: int,
    membership: Membership = Depends(require_tenant_membership),
):
    import os

    from app.n8n_client import N8NClientError, n8n_get

    if membership.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="No tienes permisos para consultar automatizaciones",
        )

    configured_tenant = int(os.environ["N8N_WORKFLOW_TENANT_ID"])

    if membership.tenant_id != configured_tenant:
        raise HTTPException(
            status_code=404,
            detail="Automatización no disponible para esta organización",
        )

    workflow_id = os.environ["N8N_WORKFLOW_ID"]

    try:
        workflow = n8n_get(f"workflows/{workflow_id}")
        executions = n8n_get(
            "executions",
            {"workflowId": workflow_id, "limit": 20},
        )
    except N8NClientError:
        raise HTTPException(
            status_code=502,
            detail="No fue posible consultar el estado de n8n",
        )

    records = executions.get("data", [])

    return {
        "workflow": {
            "id": workflow.get("id"),
            "name": workflow.get("name"),
            "active": workflow.get("active"),
            "archived": workflow.get("isArchived"),
        },
        "executions": [
            {
                "id": record.get("id"),
                "status": record.get("status"),
                "started_at": record.get("startedAt"),
                "stopped_at": record.get("stoppedAt"),
            }
            for record in records
        ],
    }


def acquire_automation_lock(connection, tenant_id: int) -> bool:
    return bool(
        connection.execute(
            text("SELECT pg_try_advisory_lock(:namespace, :tenant_id)"),
            {"namespace": 48001, "tenant_id": tenant_id},
        ).scalar_one()
    )


def release_automation_lock(connection, tenant_id: int) -> None:
    released = connection.execute(
        text("SELECT pg_advisory_unlock(:namespace, :tenant_id)"),
        {"namespace": 48001, "tenant_id": tenant_id},
    ).scalar_one()

    if not released:
        raise RuntimeError("No se pudo confirmar la liberación del bloqueo")


@app.post("/tenants/{tenant_id}/automations/{action}")
def control_automation(
    tenant_id: int,
    action: str,
    membership: Membership = Depends(require_tenant_membership),
):
    import logging
    import os

    from app.n8n_client import N8NClientError, n8n_control_workflow, verify_workflow_action

    if membership.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="No tienes permisos para administrar automatizaciones",
        )

    configured_tenant = int(os.environ["N8N_WORKFLOW_TENANT_ID"])

    if tenant_id != configured_tenant or membership.tenant_id != configured_tenant:
        raise HTTPException(
            status_code=404,
            detail="Automatización no disponible para esta organización",
        )

    if action not in ("activate", "deactivate"):
        raise HTTPException(status_code=400, detail="Acción no permitida")

    workflow_id = os.environ["N8N_WORKFLOW_ID"]

    with engine.connect() as lock_connection:
        if not acquire_automation_lock(lock_connection, tenant_id):
            raise HTTPException(
                status_code=409,
                detail="Otra operación administrativa está en curso",
            )

        try:
            with SessionLocal() as audit_db:
                pending_audit = audit_db.scalar(
                    select(AutomationAudit.id)
                    .where(
                        AutomationAudit.tenant_id == tenant_id,
                        AutomationAudit.workflow_id == workflow_id,
                        AutomationAudit.status == "pending",
                    )
                    .limit(1)
                )

                if pending_audit is not None:
                    raise HTTPException(
                        status_code=409,
                        detail="Existe una operación pendiente de revisión",
                    )

            try:
                with SessionLocal() as audit_db:
                    audit = AutomationAudit(
                        tenant_id=tenant_id,
                        user_id=membership.user_id,
                        workflow_id=workflow_id,
                        action=action,
                        status="pending",
                    )
                    audit_db.add(audit)
                    audit_db.commit()
                    audit_id = audit.id
            except SQLAlchemyError:
                logging.getLogger(__name__).exception(
                    "No fue posible iniciar la auditoría"
                )
                raise HTTPException(
                    status_code=503,
                    detail="No fue posible registrar la solicitud",
                )

            workflow = None
            operation_error = None

            try:
                workflow = n8n_control_workflow(workflow_id, action)
                verification = verify_workflow_action(workflow_id, action)

                if (
                    workflow.get("active") is (action == "activate")
                    and verification["matches_expected"]
                ):
                    result = "success"
                else:
                    result = "pending"

            except N8NClientError as exc:
                logging.getLogger(__name__).warning(
                    "Error de control n8n: tenant=%s workflow=%s action=%s audit=%s error=%s",
                    tenant_id,
                    workflow_id,
                    action,
                    audit_id,
                    exc,
                )
                operation_error = exc
                result = "pending"

            try:
                with SessionLocal() as audit_db:
                    audit = audit_db.get(AutomationAudit, audit_id)
                    if audit is None:
                        raise RuntimeError("Registro de auditoría inexistente")
                    audit.status = result
                    audit_db.commit()
            except (SQLAlchemyError, RuntimeError):
                logging.getLogger(__name__).exception(
                    "No fue posible finalizar la auditoría %s", audit_id
                )
                raise HTTPException(
                    status_code=503,
                    detail="Estado de operación no confirmado; verifica n8n",
                )

            if operation_error is not None:
                raise HTTPException(
                    status_code=502,
                    detail="Resultado no confirmado; consulta el estado de n8n antes de reintentar",
                )

            if result == "pending":
                raise HTTPException(
                    status_code=409,
                    detail="El estado del workflow no pudo confirmarse; requiere revisión",
                )

            return {
                "workflow": {
                    "id": workflow.get("id"),
                    "name": workflow.get("name"),
                    "active": workflow.get("active"),
                },
                "action": action,
            }

        finally:
            try:
                release_automation_lock(lock_connection, tenant_id)
            except Exception:
                lock_connection.invalidate()
                logging.getLogger(__name__).exception(
                    "Error al liberar el bloqueo del tenant %s",
                    tenant_id,
                )
                raise