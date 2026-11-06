import uuid
from sqlalchemy import UUID
from sqlalchemy import Integer
from sqlalchemy import text
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str | None] = mapped_column(String(150))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id"),
        UniqueConstraint("tenant_id", "id"),
        Index("idx_customers_tenant", "tenant_id"),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id"), nullable=False
    )
    customer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="open"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
        ),
        CheckConstraint("status IN ('open', 'closed', 'archived')"),
        Index("idx_conversations_customer", "tenant_id", "customer_id"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id"), nullable=False
    )
    conversation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta_message_id: Mapped[str | None] = mapped_column(String(255))
    inbound_message_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
        ),
        CheckConstraint("direction IN ('inbound', 'outbound')"),
        UniqueConstraint("tenant_id", "id", name="uq_messages_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "inbound_message_id"],
            ["messages.tenant_id", "messages.id"],
            name="fk_messages_inbound_source",
        ),
        Index(
            "uq_messages_meta_inbound",
            "tenant_id",
            "meta_message_id",
            unique=True,
            postgresql_where=text(
                "direction = 'inbound' AND meta_message_id IS NOT NULL"
            ),
        ),
        Index(
            "uq_messages_outbound_source",
            "tenant_id",
            "inbound_message_id",
            unique=True,
            postgresql_where=text(
                "direction = 'outbound' AND inbound_message_id IS NOT NULL"
            ),
        ),
        Index(
            "idx_messages_conversation",
            "tenant_id",
            "conversation_id",
            "created_at",
        ),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        nullable=False, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="agent"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id"),
        CheckConstraint("role IN ('owner', 'admin', 'agent')"),
        Index("idx_memberships_tenant", "tenant_id"),
    )


class AutomationAudit(Base):
    __tablename__ = "automation_audit"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    action: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("action IN ('activate', 'deactivate')"),
        CheckConstraint("status IN ('pending', 'success', 'failed')"),
        Index(
            "idx_automation_audit_tenant",
            "tenant_id",
            "created_at",
        ),
    )


class WhatsAppInboundEvent(Base):
    __tablename__ = "whatsapp_inbound_events"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id"), nullable=False
    )
    meta_message_id: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sender_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    message_body: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    claim_token: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True)
    )

    __table_args__ = (
        UniqueConstraint("phone_number_id", "meta_message_id"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'processed', 'failed')"
        ),
        Index("idx_whatsapp_events_tenant", "tenant_id", "created_at"),
    )


class WhatsAppOutboundDelivery(Base):
    __tablename__ = "whatsapp_outbound_deliveries"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id"), nullable=False
    )
    message_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )
    recipient_phone: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    meta_message_id: Mapped[str | None] = mapped_column(
        String(255)
    )
    last_error: Mapped[str | None] = mapped_column(Text)

    claim_token: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["messages.tenant_id", "messages.id"],
            name="fk_outbound_message",
        ),
        UniqueConstraint(
            "tenant_id",
            "message_id",
            name="uq_outbound_delivery_message",
        ),
        CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'unknown')",
            name="chk_outbound_delivery_status",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="chk_outbound_attempts",
        ),
        Index(
            "idx_outbound_delivery_status",
            "status",
            "created_at",
        ),
    )



class MessengerOutboundDelivery(Base):
    __tablename__ = "messenger_outbound_deliveries"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_id: Mapped[str] = mapped_column(String(100), nullable=False)
    recipient_psid: Mapped[str] = mapped_column(String(150), nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    meta_message_id: Mapped[str | None] = mapped_column(String(255))
    claim_token: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "message_id"],
            ["messages.tenant_id", "messages.id"],
            name="fk_messenger_outbound_message",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "page_id"],
            ["messenger_pages.tenant_id", "messenger_pages.page_id"],
            name="fk_messenger_outbound_page",
        ),
        UniqueConstraint(
            "tenant_id", "message_id",
            name="uq_messenger_outbound_message",
        ),
    )


class MessengerPage(Base):
    __tablename__ = "messenger_pages"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id"), nullable=False
    )
    page_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    page_name: Mapped[str | None] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(
        nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "page_id",
            name="uq_messenger_page_tenant",
        ),
    )
