from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)


class TenantResponse(TenantCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=150)
    name: str | None = Field(default=None, max_length=150)


class CustomerResponse(CustomerCreate):
    id: int
    tenant_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationCreate(BaseModel):
    customer_id: int = Field(gt=0)
    channel: str = Field(min_length=1, max_length=30)


class ConversationResponse(ConversationCreate):
    id: int
    tenant_id: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageCreate(BaseModel):
    conversation_id: int = Field(gt=0)
    direction: str = Field(pattern="^(inbound|outbound)$")
    content: str = Field(min_length=1)


class MessageResponse(MessageCreate):
    id: int
    tenant_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ServiceMessageCreate(BaseModel):
    cliente_id: str = Field(min_length=1, max_length=150)
    mensaje: str = Field(min_length=1)

class ServiceMessageResponse(BaseModel):
    tenant_id: int
    customer_id: int
    conversation_id: int
    message_id: int
    status: str


class ServiceOutboundMessageCreate(BaseModel):
    conversation_id: int = Field(gt=0)
    respuesta: str = Field(min_length=1)


class ServiceOutboundMessageResponse(BaseModel):
    tenant_id: int
    conversation_id: int
    message_id: int
    direction: str
    status: str

class ConversationListResponse(ConversationResponse):
    customer_name: str | None = None
    customer_external_id: str
    last_message: str | None = None
    last_message_at: datetime | None = None
