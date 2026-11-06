"""Real PostgreSQL/HTTP tests; opt in only with a disposable omni_test database."""
import hashlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from app.main import app
from app.database import SessionLocal
from app.models import (Tenant, User, Membership, Customer, Conversation, Message,
    WebsiteSite, VisitorSession, WhatsAppOutboundDelivery, MessengerPage, MessengerOutboundDelivery)
from app.security import create_access_token, hash_password
from app.message_service import enqueue_reply
from app.widget import SiteCreate
from pydantic import ValidationError

integration = pytest.mark.skipif(not os.environ.get('OMNI_TEST_DATABASE_URL'), reason='Requires disposable PostgreSQL')


def test_origin_rejects_paths_and_credentials():
    for origin in ['http://mosfix.example', 'https://mosfix.example/', 'https://u:p@mosfix.example', 'https://mosfix.example/path']:
        with pytest.raises(ValidationError):
            SiteCreate(name='Test', origin=origin)


def test_invalid_signatures_do_not_access_database(monkeypatch):
    monkeypatch.setenv('META_APP_SECRET', 'test-secret')
    with TestClient(app) as client:
        for channel in ['whatsapp', 'messenger']:
            assert client.post('/webhooks/'+channel, json={}, headers={'X-Hub-Signature-256':'sha256=invalid'}).status_code == 403
        assert client.post('/auth/login', content=b'x'*1048577).status_code == 413
        assert client.get('/auth/me', headers={'Authorization':'Bearer invalid'}).status_code == 401


@pytest.fixture(scope='module')
def seeded():
    if not os.environ.get('OMNI_TEST_DATABASE_URL'):
        pytest.skip('Requires disposable PostgreSQL')
    assert os.environ['OMNI_TEST_DATABASE_URL'].endswith('/omni_test'), 'Only disposable omni_test is permitted'
    with SessionLocal.begin() as db:
        t = Tenant(name='Widget test'); other = Tenant(name='Other tenant')
        db.add_all([t, other]);db.flush()
        users = [User(email=f'{uuid.uuid4()}@test.invalid',password_hash=hash_password('test-password')) for _ in range(3)]
        db.add_all(users);db.flush()
        for user, role in zip(users,['owner','agent','agent']):
            db.add(Membership(tenant_id=t.id if role=='owner' or user==users[1] else other.id,user_id=user.id,role=role))
        site = WebsiteSite(tenant_id=t.id,public_id=uuid.uuid4().hex,name='Mosfix',origin='https://mosfix.example')
        db.add(site);db.flush()
        return {'tenant':t.id,'other':other.id,'site':site.public_id,'site_pk':site.id,
                'users':[u.id for u in users],'tokens':[create_access_token(u.id) for u in users]}


def bearer(token):
    return {'Authorization':'Bearer '+token}


@integration
def test_visitor_full_contract_and_isolation(seeded):
    with TestClient(app) as c:
        url='/api/v1/widget/session'
        assert c.post(url,json={'site_id':seeded['site']}).status_code==403
        origin={'Origin':'https://mosfix.example'}
        pre=c.options(url,headers={**origin,'Access-Control-Request-Method':'POST'})
        assert pre.status_code==204 and pre.headers['Access-Control-Allow-Origin']==origin['Origin']
        session=c.post(url,json={'site_id':seeded['site']},headers=origin)
        assert session.status_code==201, session.text
        data=session.json(); token=data['token']; cid=data['conversation_id']; headers={**origin,**bearer(token)}
        with SessionLocal() as db:
            stored=db.scalar(select(VisitorSession).where(VisitorSession.conversation_id==cid))
            assert stored.token_hash==hashlib.sha256(token.encode()).hexdigest() and stored.token_hash!=token
        path=f'/api/v1/widget/conversations/{cid}/messages'
        assert c.get(path,headers={**headers,'Origin':'https://evil.example'}).status_code==403
        assert c.get(f'/api/v1/widget/conversations/{cid+1000}/messages',headers=headers).status_code==404
        payload={'content':'Necesito ayuda','idempotency_key':'first'}
        first=c.post(path,json=payload,headers=headers);again=c.post(path,json=payload,headers=headers)
        assert first.status_code==201, first.text
        assert first.json()['id']==again.json()['id']
        assert c.post(path,json={**payload,'content':'different'},headers=headers).status_code==409
        api_headers=bearer(seeded['tokens'][0])
        reply=c.post(f'/tenants/{seeded["tenant"]}/messages',json={'conversation_id':cid,'direction':'outbound','content':'Hola','idempotency_key':'operator-first'},headers=api_headers)
        assert reply.status_code==201, reply.text
        assert reply.json()['delivery_status']=='available'
        page=c.get(path+'?limit=1',headers=headers).json()
        assert page['has_more'] and len(page['messages'])==1
        page2=c.get(path+f'?after_id={page["next_after_id"]}',headers=headers).json()
        assert page2['messages'][0]['content']=='Hola'
        other_headers=bearer(seeded['tokens'][2])
        assert c.get(f'/tenants/{seeded["tenant"]}/conversations',headers=other_headers).status_code==403
        assert c.get(f'/tenants/{seeded["other"]}/conversations/{cid}/messages',headers=other_headers).status_code==404
        renewed=c.post(url+'/renew',headers=headers)
        assert renewed.status_code==200
        assert c.get(path,headers=headers).status_code==401
        headers={**origin,**bearer(renewed.json()['token'])}
        assert c.delete(url,headers=headers).status_code==204
        assert c.get(path,headers=headers).status_code==401


@integration
def test_operational_roles_notes_and_filters(seeded):
    with SessionLocal.begin() as db:
        customer=Customer(tenant_id=seeded['tenant'],external_id=uuid.uuid4().hex,name='Searchable Alice')
        db.add(customer);db.flush()
        conv=Conversation(tenant_id=seeded['tenant'],customer_id=customer.id,channel='website');db.add(conv);db.flush();cid=conv.id
    with TestClient(app) as c:
        base=f'/tenants/{seeded["tenant"]}';path=base+f'/conversations/{cid}'
        owner=bearer(seeded['tokens'][0]);agent=bearer(seeded['tokens'][1])
        assert c.put(path+'/assignment',json={'user_id':seeded['users'][2]},headers=owner).status_code==422
        assert c.put(path+'/assignment',json={'user_id':seeded['users'][1]},headers=agent).status_code==200
        assert c.put(path+'/assignment',json={'user_id':None},headers=agent).status_code==403
        assigned=c.get(base+'/conversations?assigned_to_me=true&q=Alice',headers=agent).json()
        assert cid in [x['id'] for x in assigned]
        assert c.post(path+'/notes',json={'content':'Internal only'},headers=agent).status_code==201
        assert c.get(path+'/messages',headers=owner).json()==[]
        assert any(x['kind']=='note' for x in c.get(path+'/events',headers=owner).json())
        assert c.post(base+'/websites',json={'name':'No','origin':'https://no.example'},headers=agent).status_code==403
        assert c.put(base+f'/members/{seeded["users"][0]}',json={'role':'agent'},headers=owner).status_code==409
        assert c.put(base+f'/members/{seeded["users"][1]}',json={'role':'admin'},headers=agent).status_code==403
        assert c.put(path+'/intervention',json={'automation_enabled':False},headers=agent).status_code==200


@integration
@pytest.mark.parametrize('channel',['whatsapp','messenger'])
def test_concurrent_reply_creates_one_outbox(seeded,channel):
    with SessionLocal.begin() as db:
        page_id='1234567'+str(seeded['tenant'])
        external='50370001234' if channel=='whatsapp' else f'fb:{page_id}:98765'
        customer=Customer(tenant_id=seeded['tenant'],external_id=external);db.add(customer);db.flush()
        conv=Conversation(tenant_id=seeded['tenant'],customer_id=customer.id,channel=channel);db.add(conv)
        if channel=='messenger':db.add(MessengerPage(tenant_id=seeded['tenant'],page_id=page_id,is_active=True))
        db.flush();cid=conv.id
    def send(_):
        with SessionLocal.begin() as db:
            conv=db.get(Conversation,cid)
            return enqueue_reply(db,conv,'One reply',idempotency_key='same-request').id
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids=list(pool.map(send,range(4)))
    assert len(set(ids))==1
    model=WhatsAppOutboundDelivery if channel=='whatsapp' else MessengerOutboundDelivery
    with SessionLocal() as db:
        assert db.scalar(select(func.count(model.id)).where(model.message_id==ids[0]))==1
    with SessionLocal() as db:
        conv=db.get(Conversation,cid)
        enqueue_reply(db,conv,'Rollback',idempotency_key='rolled-back')
        db.rollback()
    with SessionLocal() as db:
        assert db.scalar(select(Message.id).where(Message.conversation_id==cid, Message.idempotency_key=='rolled-back')) is None


@integration
def test_worker_claim_recovery_and_stale_owner(seeded, monkeypatch):
    from app import whatsapp_outbound_worker as worker
    monkeypatch.setattr(worker, 'TENANT_ID', seeded['tenant'])
    with SessionLocal.begin() as db:
        customer=Customer(tenant_id=seeded['tenant'],external_id='50370005678');db.add(customer);db.flush()
        conv=Conversation(tenant_id=seeded['tenant'],customer_id=customer.id,channel='whatsapp');db.add(conv);db.flush()
        message=enqueue_reply(db,conv,'Worker test',idempotency_key='worker-test');mid=message.id
        # Remove earlier tests' queued rows from consideration, without sending anything.
        from sqlalchemy import update
        db.execute(update(WhatsAppOutboundDelivery).where(WhatsAppOutboundDelivery.message_id!=mid).values(status='failed'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims=list(pool.map(lambda _:worker.claim_delivery(),range(4)))
    claimed=[c for c in claims if c is not None]
    assert len(claimed)==1
    delivery=claimed[0]
    assert worker.recover_interrupted_deliveries()==[]
    with SessionLocal.begin() as db:
        row=db.get(WhatsAppOutboundDelivery,delivery['id'])
        row.claimed_at=datetime.now(timezone.utc)-timedelta(minutes=6)
        row.updated_at=datetime.now(timezone.utc) # recent update must not conceal an expired claim
    assert delivery['id'] in worker.recover_interrupted_deliveries()
    assert not worker.finish_delivery(delivery['id'],'sent',delivery['claim_token'],meta_message_id='provider-id')
    with SessionLocal() as db:
        assert db.get(WhatsAppOutboundDelivery,delivery['id']).status=='unknown'


@integration
def test_internal_retry_ids_and_human_intervention(seeded, monkeypatch):
    monkeypatch.setenv('N8N_API_KEY','test-service-key')
    monkeypatch.setenv('N8N_TENANT_ID',str(seeded['tenant']))
    with TestClient(app) as c:
        data={'cliente_id':'50371112222','mensaje':'Hola','meta_message_id':uuid.uuid4().hex}
        assert c.post('/internal/messages/inbound',json=data).status_code==401
        headers={'X-Service-Key':'test-service-key'}
        first=c.post('/internal/messages/inbound',json=data,headers=headers)
        assert first.status_code==201, first.text
        first=first.json()
        again=c.post('/internal/messages/inbound',json=data,headers=headers).json()
        assert again['message_id']==first['message_id'] and again['status']=='duplicate'
        out={'conversation_id':first['conversation_id'],'respuesta':'Ayuda','inbound_message_id':first['message_id']}
        a=c.post('/internal/messages/outbound',json=out,headers=headers)
        b=c.post('/internal/messages/outbound',json=out,headers=headers)
        assert a.status_code==201 and a.json()['message_id']==b.json()['message_id']
        assert b.json()['status']=='duplicate'
        assert c.post('/internal/messages/outbound',json={'conversation_id':out['conversation_id'],'respuesta':'No ID'},headers=headers).status_code==422
        path=f'/tenants/{seeded["tenant"]}/conversations/{out["conversation_id"]}/intervention'
        assert c.put(path,json={'automation_enabled':False},headers=bearer(seeded['tokens'][0])).status_code==200
        assert c.post('/internal/messages/outbound',json=out,headers=headers).status_code==409


@integration
def test_expiration_cors_and_site_deactivation(seeded):
    with TestClient(app) as c:
        origin={'Origin':'https://mosfix.example'}
        data=c.post('/api/v1/widget/session',json={'site_id':seeded['site']},headers=origin).json()
        headers={**origin,**bearer(data['token'])}
        path=f'/api/v1/widget/conversations/{data["conversation_id"]}/messages'
        with SessionLocal.begin() as db:
            row=db.scalar(select(VisitorSession).where(VisitorSession.conversation_id==data['conversation_id']))
            row.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        response=c.get(path,headers=headers)
        assert response.status_code==401 and response.headers['access-control-allow-origin']==origin['Origin']
        other=c.post('/api/v1/widget/session',json={'site_id':seeded['site']},headers=origin).json()
        assert c.delete(f'/tenants/{seeded["tenant"]}/websites/{seeded["site_pk"]}',headers=bearer(seeded['tokens'][0])).status_code==204
        assert c.get(f'/api/v1/widget/conversations/{other["conversation_id"]}/messages',headers={**origin,**bearer(other['token'])}).status_code==401


@integration
def test_database_rate_limit_is_shared():
    from app.rate_limit import consume
    from fastapi import HTTPException
    key='test:'+uuid.uuid4().hex
    with SessionLocal() as db:
        consume(db,key,2);db.rollback()
    with SessionLocal() as db:
        consume(db,key,2)
        with pytest.raises(HTTPException) as error: consume(db,key,2)
    assert error.value.status_code==429


def test_n8n_workflow_propagates_event_identifiers():
    import json
    from pathlib import Path
    workflow=json.loads((Path(__file__).parents[2]/'automation'/'recepcion-mensajes.json').read_text())
    nodes={n['name']:n for n in workflow['nodes']}
    assert nodes['Webhook']['parameters']['authentication']=='headerAuth'
    params=nodes['HTTP Request']['parameters']['bodyParameters']['parameters']
    assert any(p['name']=='meta_message_id' for p in params)
    for name in ['Registrar respuesta - Información','Registrar respuesta - General']:
        assert any(p['name']=='inbound_message_id' for p in nodes[name]['parameters']['bodyParameters']['parameters'])


@integration
def test_failed_migration_rolls_back_schema_and_ledger(tmp_path):
    import subprocess, sys
    from pathlib import Path
    from sqlalchemy import text
    name='999_test_atomic_failure.sql'
    (tmp_path/name).write_text('CREATE TABLE test_migration_must_rollback (id INT); SELECT nonexistent_column;')
    result=subprocess.run([sys.executable,str(Path(__file__).parents[1]/'scripts'/'migrate.py')],
                          env={**os.environ,'MIGRATIONS_DIR':str(tmp_path)},capture_output=True,text=True)
    assert result.returncode!=0
    with SessionLocal() as db:
        assert db.scalar(text("SELECT to_regclass('test_migration_must_rollback')")) is None
        assert db.scalar(text('SELECT count(*) FROM schema_migrations WHERE version=:version'),{'version':name})==0


@integration
def test_migrations_from_empty_schema_and_checksum_guard(tmp_path):
    import subprocess, sys, shutil
    from pathlib import Path
    from sqlalchemy import text
    schema='migration_test_'+uuid.uuid4().hex
    root=Path(__file__).parents[2]
    with SessionLocal.begin() as db:
        db.execute(text('CREATE SCHEMA '+schema))
    env={**os.environ,'DATABASE_URL':os.environ['OMNI_TEST_DATABASE_URL']+'?options=-csearch_path%3D'+schema}
    command=[sys.executable,str(root/'backend'/'scripts'/'migrate.py')]
    try:
        first=subprocess.run(command,env=env,capture_output=True,text=True)
        assert first.returncode==0, first.stderr
        second=subprocess.run(command,env=env,capture_output=True,text=True)
        assert second.returncode==0 and 'Ya aplicada: 016_' in second.stdout
        shutil.copytree(root/'database'/'migrations',tmp_path/'migrations')
        path=tmp_path/'migrations'/'001_initial_schema.sql'
        path.write_text(path.read_text()+'\n-- unexpected historical edit\n')
        changed=subprocess.run(command,env={**env,'MIGRATIONS_DIR':str(tmp_path/'migrations')},capture_output=True,text=True)
        assert changed.returncode!=0 and 'Migración aplicada modificada' in changed.stderr
    finally:
        with SessionLocal.begin() as db:
            db.execute(text('DROP SCHEMA '+schema+' CASCADE'))
