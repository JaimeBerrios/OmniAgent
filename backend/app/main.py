from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .database import engine, get_db
from .models import Conversation, Customer, Membership, Message, Tenant, User
from .service_security import require_service_key
from .schemas import (
    ConversationCreate,
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
