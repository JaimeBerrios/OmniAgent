"""Website outbox tests against an explicitly supplied disposable PostgreSQL."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, select
from app.database import SessionLocal
from app.main import app
from app.models import Tenant, WebsiteSite, Conversation, Message
from app import website_worker as worker

pytestmark = pytest.mark.skipif(not os.getenv('OMNI_TEST_DATABASE_URL'), reason='Disposable PostgreSQL required')


@pytest.fixture
def website(monkeypatch):
    assert os.environ['OMNI_TEST_DATABASE_URL'].endswith('/omni_test')
    with SessionLocal.begin() as db:
        # Isolate worker queue from other tests; this database is disposable.
        db.execute(text("UPDATE website_inbound_events SET status='cancelled',claim_token=NULL,processing_started_at=NULL"))
        tenant = Tenant(name='Website test'); db.add(tenant); db.flush()
        site = WebsiteSite(tenant_id=tenant.id, public_id=uuid.uuid4().hex,
                           name='Mosfix', origin='https://mosfix.example')
        db.add(site); db.flush(); tid=tenant.id; sid=site.public_id
    monkeypatch.setenv('N8N_API_KEY', 'website-test-service')
    monkeypatch.setenv('N8N_TENANT_ID', str(tid))
    monkeypatch.setenv('N8N_WEBHOOK_KEY', 'website-test-webhook')
    monkeypatch.setenv('N8N_WEBHOOK_URL', 'http://n8n:5678/webhook/omniagent-website')
    with TestClient(app) as client:
        result=client.post('/api/v1/widget/session',json={'site_id':sid},headers={'Origin':'https://mosfix.example'})
        assert result.status_code==201
        data=result.json()
        yield client, tid, data['conversation_id'], {'Origin':'https://mosfix.example','Authorization':'Bearer '+data['token']}


def send(website, key='first'):
    client, _, cid, headers=website
    return client.post(f'/api/v1/widget/conversations/{cid}/messages',json={'content':'Ayuda','idempotency_key':key},headers=headers)


def count_events(cid):
    with SessionLocal() as db:
        return db.scalar(text('SELECT count(*) FROM website_inbound_events WHERE conversation_id=:cid'),{'cid':cid})


def test_atomic_and_idempotent(website, monkeypatch):
    client, _, cid, _=website
    from sqlalchemy.orm import Session
    original=Session.execute
    def fail(self, statement, *args, **kwargs):
        if 'INSERT INTO website_inbound_events' in str(statement):
            raise RuntimeError('outbox unavailable')
        return original(self, statement, *args, **kwargs)
    with patch.object(Session, 'execute', fail):
        with pytest.raises(RuntimeError): send(website)
    with SessionLocal() as db:
        assert db.scalar(select(Message.id).where(Message.conversation_id==cid)) is None
    assert count_events(cid)==0
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(lambda _:send(website),range(4)))
    assert all(r.status_code==201 for r in responses)
    assert len({r.json()['id'] for r in responses})==1
    assert count_events(cid)==1


def test_claim_concurrency_expiry_and_stale_owner(website):
    assert send(website).status_code==201
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims=list(pool.map(lambda _:worker.claim_event(),range(4)))
    claims=[c for c in claims if c]
    assert len(claims)==1
    old=claims[0]
    with SessionLocal.begin() as db:
        db.execute(text("UPDATE website_inbound_events SET processing_started_at=NOW()-INTERVAL '6 minutes' WHERE id=:id"),old)
    new=worker.claim_event()
    assert new['claim_token']!=old['claim_token'] and new['attempts']==2
    assert not worker.finish_event(old,'processed')
    assert worker.finish_event(new,'failed')
    assert worker.claim_event() is None  # backoff


@pytest.mark.parametrize('failure',[TimeoutError, RuntimeError])
def test_n8n_failure_and_retry(website, monkeypatch, failure):
    send(website)
    event=worker.claim_event()
    monkeypatch.setattr(worker.urllib.request,'urlopen',lambda *a,**kw: (_ for _ in ()).throw(failure()))
    with pytest.raises(failure): worker.process_event(event)
    worker.fail_event(event,failure())
    with SessionLocal() as db:
        row=db.execute(text('SELECT status,next_retry_at,claim_token FROM website_inbound_events WHERE id=:id'),event).one()
        assert row.status=='failed' and row.next_retry_at>datetime.now(timezone.utc) and row.claim_token is None


def test_http_200_requires_persisted_reply_and_retry_is_safe(website, monkeypatch):
    import json
    client, tid, cid, _=website
    inbound=send(website).json()['id']; event=worker.claim_event()
    class Response:
        status=200
        def __enter__(self): return self
        def __exit__(self,*a): pass
    monkeypatch.setattr(worker.urllib.request,'urlopen',lambda *a,**kw:Response())
    with pytest.raises(RuntimeError,match='not persisted'): worker.process_event(event)
    def callback(request,timeout):
        payload=json.loads(request.data)
        assert set(payload)=={'tenant_id','site_id','conversation_id','inbound_message_id','mensaje','canal'}
        # Network callback can take the conversation lock: no worker transaction is open.
        response=client.post('/internal/messages/outbound',json={'conversation_id':cid,'inbound_message_id':inbound,'respuesta':'Respuesta del proveedor de prueba'},headers={'X-Service-Key':'website-test-service'})
        assert response.status_code==201, response.text
        return Response()
    monkeypatch.setattr(worker.urllib.request,'urlopen',callback)
    worker.process_event(event)
    # Redelivery after callback persisted must avoid generating another reply.
    assert client.post('/internal/messages/outbound',json={'conversation_id':cid,'inbound_message_id':inbound,'respuesta':'Different retry'},headers={'X-Service-Key':'website-test-service'}).json()['status']=='duplicate'
    with SessionLocal() as db:
        assert db.scalar(text("SELECT status FROM website_inbound_events WHERE id=:id"),event)=='processed'
        assert db.scalar(text("SELECT count(*) FROM messages WHERE inbound_message_id=:mid"),{'mid':inbound})==1
    history=client.get(f'/api/v1/widget/conversations/{cid}/messages',headers=website[3]).json()
    assert len(history['messages'])==2


@pytest.mark.parametrize('change',['automation','closed','site'])
def test_authorization_rechecked_before_dispatch_and_callback(website, monkeypatch, change):
    client, tid, cid, _=website
    inbound=send(website).json()['id']; event=worker.claim_event()
    with SessionLocal.begin() as db:
        if change=='site': db.execute(text('UPDATE website_sites SET is_active=false WHERE tenant_id=:tid'),{'tid':tid})
        else:
            conv=db.get(Conversation,cid)
            if change=='automation': conv.automation_enabled=False
            else: conv.status='closed'
    monkeypatch.setattr(worker.urllib.request,'urlopen',lambda *a,**k:pytest.fail('HTTP must not run'))
    worker.process_event(event)
    assert client.post('/internal/messages/outbound',json={'conversation_id':cid,'inbound_message_id':inbound,'respuesta':'Blocked'},headers={'X-Service-Key':'website-test-service'}).status_code==409
    with SessionLocal() as db:
        assert db.scalar(text('SELECT status FROM website_inbound_events WHERE id=:id'),event)=='cancelled'
    if change=='automation':
        assert send(website,'human').status_code==201
        assert count_events(cid)==1
    if change=='closed': assert send(website,'closed').status_code==409


def test_callback_tenant_isolation(website,monkeypatch):
    client, _, cid, _=website
    inbound=send(website).json()['id']
    monkeypatch.setenv('N8N_TENANT_ID','99999999')
    assert client.post('/internal/messages/outbound',json={'conversation_id':cid,'inbound_message_id':inbound,'respuesta':'Blocked'},headers={'X-Service-Key':'website-test-service'}).status_code==404


def test_lost_http_response_recovers_without_another_ai_call(website, monkeypatch):
    client, _, cid, _=website
    inbound=send(website).json()['id']; event=worker.claim_event()
    response=client.post('/internal/messages/outbound',json={'conversation_id':cid,'inbound_message_id':inbound,'respuesta':'Saved before network timeout'},headers={'X-Service-Key':'website-test-service'})
    assert response.status_code==201
    worker.fail_event(event,TimeoutError())
    with SessionLocal.begin() as db:
        db.execute(text("UPDATE website_inbound_events SET next_retry_at=NOW()-INTERVAL '1 second' WHERE id=:id"),event)
    retry=worker.claim_event()
    assert retry['attempts']==2
    monkeypatch.setattr(worker.urllib.request,'urlopen',lambda *a,**k:pytest.fail('Already persisted'))
    worker.process_event(retry)
    with SessionLocal() as db:
        assert db.scalar(text('SELECT status FROM website_inbound_events WHERE id=:id'),event)=='processed'


def test_http_error_is_retried(website,monkeypatch):
    import urllib.error
    send(website); event=worker.claim_event()
    def unavailable(*args,**kwargs):
        raise urllib.error.HTTPError('http://n8n',503,'Unavailable',{},None)
    monkeypatch.setattr(worker.urllib.request,'urlopen',unavailable)
    with pytest.raises(urllib.error.HTTPError) as error: worker.process_event(event)
    worker.fail_event(event,error.value)
    with SessionLocal() as db:
        row=db.execute(text('SELECT status,last_error FROM website_inbound_events WHERE id=:id'),event).one()
        assert row.status=='failed' and row.last_error=='HTTPError'
