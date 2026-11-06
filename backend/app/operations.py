"""Tenant operator tools. Notes are never external messages."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from .database import get_db
from .models import Conversation, ConversationEvent, Message, Membership, User, Tenant, AdminEvent
from .security import require_tenant_membership, get_current_user
router = APIRouter(tags=['Operations'])


def event(db, membership, conversation_id, kind, content):
    db.add(ConversationEvent(tenant_id=membership.tenant_id, actor_id=membership.user_id,
           conversation_id=conversation_id, kind=kind, content=content))


def get_conversation(db, membership, conversation_id):
    c = db.scalar(select(Conversation).where(Conversation.tenant_id == membership.tenant_id,
                     Conversation.id == conversation_id).with_for_update())
    if c is None:
        raise HTTPException(404, 'Conversación no encontrada')
    return c


@router.get('/auth/organizations')
def organizations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [{'tenant_id': t.id, 'organization': t.name, 'role': m.role} for t, m in db.execute(
        select(Tenant, Membership).join(Membership, Tenant.id == Membership.tenant_id).where(Membership.user_id == user.id))]


class Assignment(BaseModel):
    user_id: int | None = Field(default=None, gt=0)


@router.put('/tenants/{tenant_id}/conversations/{conversation_id}/assignment')
def assign(tenant_id: int, conversation_id: int, data: Assignment,
           membership: Membership = Depends(require_tenant_membership), db: Session = Depends(get_db)):
    if membership.role == 'agent' and data.user_id != membership.user_id:
        raise HTTPException(403, 'Solo puedes asignarte a ti mismo')
    c = get_conversation(db, membership, conversation_id)
    if membership.role == 'agent' and c.assigned_user_id not in (None, membership.user_id):
        raise HTTPException(403, 'La conversación ya tiene un agente')
    if data.user_id is not None and db.scalar(select(Membership.id).join(User, User.id == Membership.user_id).where(
            Membership.tenant_id == membership.tenant_id, Membership.user_id == data.user_id, User.is_active.is_(True))) is None:
        raise HTTPException(422, 'El agente no pertenece a la organización')
    c.assigned_user_id = data.user_id
    event(db, membership, c.id, 'assignment', str(data.user_id))
    db.commit()
    return {'assigned_user_id': c.assigned_user_id}


class Intervention(BaseModel):
    automation_enabled: bool


@router.put('/tenants/{tenant_id}/conversations/{conversation_id}/intervention')
def intervention(tenant_id: int, conversation_id: int, data: Intervention,
                 membership: Membership = Depends(require_tenant_membership), db: Session = Depends(get_db)):
    c = get_conversation(db, membership, conversation_id)
    c.automation_enabled = data.automation_enabled
    event(db, membership, c.id, 'automation', str(data.automation_enabled))
    db.commit()
    return {'automation_enabled': c.automation_enabled}


@router.post('/tenants/{tenant_id}/conversations/{conversation_id}/read', status_code=204)
def mark_read(tenant_id: int, conversation_id: int,
              membership: Membership = Depends(require_tenant_membership), db: Session = Depends(get_db)):
    c = get_conversation(db, membership, conversation_id)
    c.last_read_message_id = db.scalar(select(func.max(Message.id)).where(
        Message.tenant_id == membership.tenant_id, Message.conversation_id == c.id))
    db.commit()


class Note(BaseModel):
    content: str = Field(min_length=1, max_length=4096)


@router.post('/tenants/{tenant_id}/conversations/{conversation_id}/notes', status_code=201)
def note(tenant_id: int, conversation_id: int, data: Note,
         membership: Membership = Depends(require_tenant_membership), db: Session = Depends(get_db)):
    c = get_conversation(db, membership, conversation_id)
    event(db, membership, c.id, 'note', data.content)
    db.commit()
    return {'status': 'recorded'}


@router.get('/tenants/{tenant_id}/conversations/{conversation_id}/events')
def events(tenant_id: int, conversation_id: int, after_id: int = Query(0, ge=0),
           membership: Membership = Depends(require_tenant_membership), db: Session = Depends(get_db)):
    get_conversation(db, membership, conversation_id)
    return [{'id': e.id, 'actor_id': e.actor_id, 'kind': e.kind, 'content': e.content, 'created_at': e.created_at}
        for e in db.scalars(select(ConversationEvent).where(ConversationEvent.tenant_id == membership.tenant_id,
            ConversationEvent.conversation_id == conversation_id, ConversationEvent.id > after_id).order_by(ConversationEvent.id).limit(100))]


@router.get('/tenants/{tenant_id}/members')
def members(tenant_id: int, membership: Membership = Depends(require_tenant_membership), db: Session = Depends(get_db)):
    return [{'user_id': u.id, 'email': u.email, 'role': m.role} for m, u in db.execute(
        select(Membership, User).join(User, User.id == Membership.user_id).where(Membership.tenant_id == membership.tenant_id))]


class MemberRole(BaseModel):
    role: Literal['admin', 'agent']


@router.put('/tenants/{tenant_id}/members/{user_id}')
def member_role(tenant_id: int, user_id: int, data: MemberRole,
                membership: Membership = Depends(require_tenant_membership), db: Session = Depends(get_db)):
    if membership.role != 'owner':
        raise HTTPException(403, 'Solo el propietario administra roles')
    member = db.scalar(select(Membership).where(Membership.tenant_id == membership.tenant_id, Membership.user_id == user_id).with_for_update())
    if member is None:
        raise HTTPException(404, 'Miembro no encontrado')
    if member.role == 'owner':
        raise HTTPException(409, 'El propietario no se puede degradar')
    member.role = data.role
    db.add(AdminEvent(tenant_id=membership.tenant_id, actor_id=membership.user_id,
                      action='member.role', target=f'{user_id}:{data.role}'))
    db.commit()
    return {'user_id': user_id, 'role': member.role}
