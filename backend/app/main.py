from .messenger_webhook import router as messenger_router
from .legal import router as legal_router
from .whatsapp_webhook import router as whatsapp_router
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, status, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .database import SessionLocal, engine, get_db
from .models import AutomationAudit, Conversation, Customer, Membership, Message, Tenant, User, WhatsAppOutboundDelivery, MessengerPage, MessengerOutboundDelivery
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


for whatsapp_route in whatsapp_router.routes:
    app.router.routes.append(whatsapp_route)


from .widget import router as widget_router
from .operations import router as operations_router
from .message_service import enqueue_reply
from .rate_limit import consume
from .http_safety import BodyLimitMiddleware, WidgetCORSMiddleware
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(WidgetCORSMiddleware)
app.include_router(widget_router)
app.include_router(operations_router)
app.include_router(legal_router)
for messenger_route in messenger_router.routes:
    app.router.routes.append(messenger_route)


# ----------------------------------------
# GENERAL
# ----------------------------------------

@app.get("/")
def root():
    return {
        "application": "OmniAgent",
        "status": "running",
        "version": __import__("os").environ.get("APP_VERSION", "dev"),
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
    request: Request,
    db: Session = Depends(get_db),
):
    consume(db, "login:" + (request.client.host if request.client else "unknown"), 10)
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
    after_id: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    q: str = Query("", max_length=150),
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    customers = db.scalars(
        select(Customer)
        .where(Customer.tenant_id == membership.tenant_id)
        .where(Customer.id > after_id, (Customer.name.ilike(f"%{q}%") | Customer.external_id.ilike(f"%{q}%")))
        .order_by(Customer.id).limit(limit)
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
    limit: int = Query(100, ge=1, le=500),
    before_id: int | None = Query(None, gt=0),
    q: str = Query("", max_length=150),
    channel: str | None = Query(None, max_length=30),
    status: str | None = Query(None, pattern="^(open|closed|archived)$"),
    assigned_to_me: bool = False,
    membership: Membership = Depends(require_tenant_membership),
    db: Session = Depends(get_db),
):
    latest = select(Message.id).where(Message.tenant_id == Conversation.tenant_id,
        Message.conversation_id == Conversation.id).order_by(Message.id.desc()).limit(1).correlate(Conversation).scalar_subquery()
    statement = select(Conversation, Customer, Message).join(Customer,
        (Customer.id == Conversation.customer_id) & (Customer.tenant_id == Conversation.tenant_id)
    ).outerjoin(Message, Message.id == latest).where(Conversation.tenant_id == membership.tenant_id)
    if before_id:
        statement = statement.where(Conversation.id < before_id)
    if channel:
        statement = statement.where(Conversation.channel == channel)
    statement = statement.where(Conversation.status == status) if status else statement.where(Conversation.status != "archived")
    if assigned_to_me:
        statement = statement.where(Conversation.assigned_user_id == membership.user_id)
    if q:
        statement = statement.where(Customer.name.ilike(f"%{q}%") | Customer.external_id.ilike(f"%{q}%"))
    rows = db.execute(statement.order_by(Conversation.id.desc()).limit(limit)).all()
    return [ConversationListResponse(
        **ConversationResponse.model_validate(c).model_dump(),
        customer_name=customer.name, customer_external_id=customer.external_id,
        last_message=m.content if m else None, last_message_at=m.created_at if m else None,
        pending_reply=bool(m and m.direction == "inbound" and c.status == "open"),
        unread=bool(m and m.direction == "inbound" and m.id > (c.last_read_message_id or 0)),
    ) for c, customer, m in rows]


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
    from .operations import event
    event(db, membership, conversation.id, "status", data.status)
    db.commit()
    db.refresh(conversation)

    return conversation


# ----------------------------------------
def get_messenger_delivery_status(
    db: Session,
    tenant_id: int,
    message_id: int,
) -> str | None:
    return db.scalar(
        select(MessengerOutboundDelivery.status)
        .where(
            MessengerOutboundDelivery.tenant_id == tenant_id,
            MessengerOutboundDelivery.message_id == message_id,
        )
        .limit(1)
    )


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
    consume(db, f"operator-send:{membership.tenant_id}:{membership.user_id}", 60)
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

    if message_data.direction != "outbound":
        raise HTTPException(422, "Los mensajes entrantes deben llegar por su canal")
    message = enqueue_reply(db, conversation, message_data.content,
                            idempotency_key=message_data.idempotency_key)
    from .operations import event
    event(db, membership, conversation.id, "reply", str(message.id))
    db.commit()
    response = MessageResponse.model_validate(message)
    model = {"messenger": MessengerOutboundDelivery, "whatsapp": WhatsAppOutboundDelivery}.get(conversation.channel)
    if model:
        response.delivery_status = db.scalar(select(model.status).where(
            model.tenant_id == membership.tenant_id, model.message_id == message.id))
    else:
        response.delivery_status = "available"
    return response


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
    after_id: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
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
            Message.id > after_id,
        )
        .order_by(Message.id)
        .limit(limit)
    ).all()

    delivery_model = {"messenger": MessengerOutboundDelivery, "whatsapp": WhatsAppOutboundDelivery}.get(conversation.channel)
    if delivery_model is None:
        return messages

    message_ids = [
        message.id
        for message in messages
        if message.direction == "outbound"
    ]

    if not message_ids:
        return messages

    deliveries = db.execute(
        select(
            delivery_model.message_id,
            delivery_model.status,
        ).where(
            delivery_model.tenant_id == membership.tenant_id,
            delivery_model.message_id.in_(message_ids),
        )
    ).all()

    statuses = {
        message_id: delivery_status
        for message_id, delivery_status in deliveries
    }

    responses = []

    for message in messages:
        response = MessageResponse.model_validate(message)
        response.delivery_status = statuses.get(message.id)
        responses.append(response)

    return responses


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
    if message_data.meta_message_id:
        existing = db.scalar(
            select(Message).where(
                Message.tenant_id == tenant_id,
                Message.meta_message_id == message_data.meta_message_id,
                Message.direction == "inbound",
            )
        )

        if existing is not None:
            conversation = db.scalar(
                select(Conversation).where(
                    Conversation.id == existing.conversation_id,
                    Conversation.tenant_id == tenant_id,
                )
            )

            return ServiceMessageResponse(
                tenant_id=tenant_id,
                customer_id=conversation.customer_id,
                conversation_id=existing.conversation_id,
                message_id=existing.id,
                status="duplicate",
            )

    customer = db.scalar(
        select(Customer).where(
            Customer.tenant_id == tenant_id,
            Customer.external_id == message_data.cliente_id,
        )
    )

    if customer is None:
        customer = Customer(
            tenant_id=tenant_id,
            external_id=message_data.cliente_id,
        )

        try:
            with db.begin_nested():
                db.add(customer)
                db.flush()
        except IntegrityError:
            customer = db.scalar(
                select(Customer).where(
                    Customer.tenant_id == tenant_id,
                    Customer.external_id == message_data.cliente_id,
                )
            )
            if customer is None:
                raise

    db.scalar(select(Customer).where(Customer.id == customer.id,
        Customer.tenant_id == tenant_id).with_for_update())
    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.customer_id == customer.id,
            Conversation.channel == message_data.canal,
            Conversation.status == "open",
        )
        .order_by(Conversation.id.desc())
        .limit(1)
    )

    if conversation is None:
        conversation = Conversation(
            tenant_id=tenant_id,
            customer_id=customer.id,
            channel=message_data.canal,
        )
        db.add(conversation)
        db.flush()

    message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction="inbound",
        content=message_data.mensaje,
        meta_message_id=message_data.meta_message_id,
    )

    try:
        with db.begin_nested():
            db.add(message)
            db.flush()
    except IntegrityError:
        if not message_data.meta_message_id:
            raise

        existing = db.scalar(
            select(Message).where(
                Message.tenant_id == tenant_id,
                Message.meta_message_id == message_data.meta_message_id,
                Message.direction == "inbound",
            )
        )

        if existing is None:
            raise

        conversation = db.scalar(
            select(Conversation).where(
                Conversation.id == existing.conversation_id,
                Conversation.tenant_id == tenant_id,
            )
        )

        response = ServiceMessageResponse(
            tenant_id=tenant_id,
            customer_id=conversation.customer_id,
            conversation_id=existing.conversation_id,
            message_id=existing.id,
            status="duplicate",
        )

        db.rollback()
        return response

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

    db.scalar(select(Conversation).where(Conversation.id == conversation.id,
        Conversation.tenant_id == tenant_id).with_for_update().execution_options(populate_existing=True))
    if conversation.status != 'open':
        raise HTTPException(409, "La conversación está cerrada")
    if conversation.channel == 'website':
        # The callback must belong to an event from a currently active registered site.
        from sqlalchemy import text
        if not db.scalar(text("""
            SELECT e.id FROM website_inbound_events e
            JOIN website_sites s ON s.id=e.site_id AND s.tenant_id=e.tenant_id
            WHERE e.tenant_id=:tenant AND e.conversation_id=:conversation
              AND e.message_id=:message AND s.is_active
        """), dict(tenant=tenant_id, conversation=conversation.id,
                   message=message_data.inbound_message_id)):
            raise HTTPException(409, "Evento website no autorizado")
    if not conversation.automation_enabled:
        raise HTTPException(409, "Intervención humana activa")
    if message_data.inbound_message_id is not None:
        inbound = db.scalar(
            select(Message).where(
                Message.id == message_data.inbound_message_id,
                Message.tenant_id == tenant_id,
                Message.conversation_id == conversation.id,
                Message.direction == "inbound",
            )
        )

        if inbound is None:
            raise HTTPException(
                status_code=404,
                detail="Mensaje entrante no encontrado en esta conversación",
            )

        existing = db.scalar(
            select(Message).where(
                Message.tenant_id == tenant_id,
                Message.inbound_message_id == inbound.id,
                Message.direction == "outbound",
            )
        )

        if existing is not None:
            return ServiceOutboundMessageResponse(
                tenant_id=tenant_id,
                conversation_id=existing.conversation_id,
                message_id=existing.id,
                direction="outbound",
                status="duplicate",
            )

    if message_data.inbound_message_id is None:
        raise HTTPException(422, "inbound_message_id es obligatorio para reintentos seguros")
    message = enqueue_reply(db, conversation, message_data.respuesta,
                            inbound_message_id=message_data.inbound_message_id)

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