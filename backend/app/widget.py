"""Visitor HTTP contract. Bearer tokens authorize exactly one site/conversation."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import WebsiteSite, VisitorSession, Conversation, Customer, Message, Membership, AdminEvent
from .schemas import MessageResponse
from .security import require_tenant_membership
from .rate_limit import consume

router = APIRouter(tags=['Website'])


class SiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    origin: str = Field(max_length=255)

    @field_validator('origin')
    @classmethod
    def valid_origin(cls, value):
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment):
            raise ValueError('Usa un origen HTTPS sin ruta ni barra final')
        return value


class SessionCreate(BaseModel):
    site_id: str = Field(min_length=1, max_length=64)


class VisitorMessage(BaseModel):
    content: str = Field(min_length=1, max_length=4096)
    idempotency_key: str = Field(min_length=1, max_length=92)

    @field_validator('content')
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError('El mensaje no puede estar vacío')
        return value


def site_response(site):
    return {key: getattr(site, key) for key in ('id', 'public_id', 'name', 'origin', 'is_active')}


def admin(membership):
    if membership.role not in ('owner', 'admin'):
        raise HTTPException(403, 'Se requiere un administrador')


@router.get('/tenants/{tenant_id}/websites')
def sites(tenant_id: int, membership: Membership = Depends(require_tenant_membership), db: Session = Depends(get_db)):
    admin(membership)
    return [site_response(s) for s in db.scalars(select(WebsiteSite).where(
        WebsiteSite.tenant_id == membership.tenant_id).order_by(WebsiteSite.id))]


@router.post('/tenants/{tenant_id}/websites', status_code=201)
def create_site(tenant_id: int, data: SiteCreate, membership: Membership = Depends(require_tenant_membership), db: Session = Depends(get_db)):
    admin(membership)
    site = WebsiteSite(tenant_id=membership.tenant_id, public_id=secrets.token_urlsafe(24), **data.model_dump())
    db.add(site)
    db.add(AdminEvent(tenant_id=membership.tenant_id, actor_id=membership.user_id, action="website.create", target=site.public_id))
    db.commit()
    db.refresh(site)
    return site_response(site)


@router.delete('/tenants/{tenant_id}/websites/{site_id}', status_code=204)
def deactivate_site(tenant_id: int, site_id: int, membership: Membership = Depends(require_tenant_membership), db: Session = Depends(get_db)):
    admin(membership)
    site = db.scalar(select(WebsiteSite).where(WebsiteSite.id == site_id, WebsiteSite.tenant_id == membership.tenant_id).with_for_update())
    if site is None:
        raise HTTPException(404, 'Sitio no encontrado')
    site.is_active = False
    db.add(AdminEvent(tenant_id=membership.tenant_id, actor_id=membership.user_id, action="website.deactivate", target=site.public_id))
    db.commit()


def allow_origin(request, response, site):
    if request.headers.get('origin') != site.origin:
        raise HTTPException(403, 'Origen no autorizado')
    response.headers['Access-Control-Allow-Origin'] = site.origin
    response.headers['Vary'] = 'Origin'
    response.headers['Cache-Control'] = 'no-store'


def visitor(request: Request, response: Response, db: Session = Depends(get_db)):
    auth = request.headers.get('authorization', '')
    if not auth.startswith('Bearer ') or len(auth) > 200:
        raise HTTPException(401, 'Sesión requerida')
    digest = hashlib.sha256(auth[7:].encode()).hexdigest()
    row = db.execute(select(VisitorSession, WebsiteSite).join(WebsiteSite,
        (WebsiteSite.id == VisitorSession.site_id) & (WebsiteSite.tenant_id == VisitorSession.tenant_id))
        .where(VisitorSession.token_hash == digest, VisitorSession.revoked_at.is_(None),
               VisitorSession.expires_at > datetime.now(timezone.utc), WebsiteSite.is_active.is_(True))
        .with_for_update(of=VisitorSession)).first()
    if row is None:
        raise HTTPException(401, 'Sesión inválida o expirada')
    session, site = row
    allow_origin(request, response, site)
    consume(db, f'visitor:{session.id}', 120)
    return session


@router.options('/api/v1/widget/{path:path}')
def preflight(path: str, request: Request, db: Session = Depends(get_db)):
    origin = request.headers.get('origin', '')
    allowed = db.scalar(select(WebsiteSite.id).where(WebsiteSite.origin == origin, WebsiteSite.is_active.is_(True)).limit(1))
    if not allowed or request.headers.get('access-control-request-method') not in ('GET', 'POST', 'DELETE'):
        raise HTTPException(403, 'Origen o método no autorizado')
    return Response(status_code=204, headers={'Access-Control-Allow-Origin': origin, 'Vary': 'Origin',
        'Access-Control-Allow-Methods': 'GET, POST, DELETE', 'Access-Control-Allow-Headers': 'Authorization, Content-Type',
        'Access-Control-Max-Age': '600'})


@router.post('/api/v1/widget/session', status_code=201)
def create_session(data: SessionCreate, request: Request, response: Response, db: Session = Depends(get_db)):
    site = db.scalar(select(WebsiteSite).where(WebsiteSite.public_id == data.site_id, WebsiteSite.is_active.is_(True)))
    if site is None:
        raise HTTPException(404, 'Sitio no encontrado')
    allow_origin(request, response, site)
    consume(db, f'session:{site.id}:{request.client.host if request.client else "unknown"}', 10)
    customer = Customer(tenant_id=site.tenant_id, external_id='web:' + secrets.token_urlsafe(24), name='Visitante web')
    db.add(customer)
    db.flush()
    conversation = Conversation(tenant_id=site.tenant_id, customer_id=customer.id, channel='website')
    db.add(conversation)
    db.flush()
    token = secrets.token_urlsafe(32)
    session = VisitorSession(tenant_id=site.tenant_id, site_id=site.id, conversation_id=conversation.id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=datetime.now(timezone.utc) + timedelta(hours=24))
    db.add(session)
    db.commit()
    return {'token': token, 'conversation_id': conversation.id, 'expires_at': session.expires_at}


@router.post('/api/v1/widget/session/renew')
def renew_session(session: VisitorSession = Depends(visitor), db: Session = Depends(get_db)):
    token = secrets.token_urlsafe(32)
    session.token_hash = hashlib.sha256(token.encode()).hexdigest()
    session.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    db.commit()
    return {'token': token, 'conversation_id': session.conversation_id, 'expires_at': session.expires_at}


@router.delete('/api/v1/widget/session', status_code=204)
def revoke_session(session: VisitorSession = Depends(visitor), db: Session = Depends(get_db)):
    session.revoked_at = datetime.now(timezone.utc)
    db.commit()


def owns(session, conversation_id):
    if session.conversation_id != conversation_id:
        raise HTTPException(404, 'Conversación no encontrada')


@router.post('/api/v1/widget/conversations/{conversation_id}/messages', response_model=MessageResponse, status_code=201)
def post_message(conversation_id: int, data: VisitorMessage, session: VisitorSession = Depends(visitor), db: Session = Depends(get_db)):
    owns(session, conversation_id)
    consume(db, f'visitor-send:{session.id}', 30)
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id,
            Conversation.tenant_id == session.tenant_id, Conversation.channel == 'website').with_for_update())
    if conversation is None:
        raise HTTPException(404, 'Conversación no encontrada')
    key = 'visitor:' + data.idempotency_key
    if len(key) > 100:
        raise HTTPException(422, 'La clave admite hasta 92 caracteres')
    existing = db.scalar(select(Message).where(Message.tenant_id == session.tenant_id,
        Message.conversation_id == conversation_id, Message.idempotency_key == key))
    if existing:
        if existing.content != data.content or existing.direction != 'inbound':
            raise HTTPException(409, 'La clave ya identifica otro mensaje')
        return existing
    if conversation.status != 'open':
        raise HTTPException(409, 'La conversación está cerrada')
    message = Message(tenant_id=session.tenant_id, conversation_id=conversation_id, direction='inbound',
                      content=data.content, idempotency_key=key)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.get('/api/v1/widget/conversations/{conversation_id}/messages')
def history(conversation_id: int, after_id: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
            session: VisitorSession = Depends(visitor), db: Session = Depends(get_db)):
    owns(session, conversation_id)
    rows = db.scalars(select(Message).where(Message.tenant_id == session.tenant_id,
        Message.conversation_id == conversation_id, Message.id > after_id).order_by(Message.id).limit(limit + 1)).all()
    visible = rows[:limit]
    return {'messages': [MessageResponse.model_validate(m) for m in visible],
            'next_after_id': visible[-1].id if visible else after_id, 'has_more': len(rows) > limit}
