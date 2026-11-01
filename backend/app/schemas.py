
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
