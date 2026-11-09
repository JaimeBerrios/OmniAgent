"""At-least-once website dispatch; only a persisted reply confirms completion."""
import json
import logging
import os
import time
import uuid
import urllib.request
from sqlalchemy import text
from app.database import SessionLocal

logger = logging.getLogger('omniagent.website_worker')
LEASE_SECONDS = 300
HTTP_TIMEOUT = 30
POLL_INTERVAL = 2


def claim_event():
    with SessionLocal.begin() as db:
        row = db.execute(text("""
            SELECT * FROM website_inbound_events
            WHERE (status IN ('pending','failed') AND next_retry_at <= NOW())
               OR (status='processing' AND processing_started_at < NOW() - (:lease * INTERVAL '1 second'))
            ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
        """), {'lease': LEASE_SECONDS}).mappings().first()
        if row is None:
            return None
        event = dict(row)
        event['claim_token'] = uuid.uuid4()
        event['attempts'] += 1
        db.execute(text("""
            UPDATE website_inbound_events SET status='processing', attempts=attempts+1,
                processing_started_at=NOW(), updated_at=NOW(), claim_token=:claim_token
            WHERE id=:id
        """), event)
        return event


def finish_event(event, status, error=None):
    if status not in ('processed', 'failed', 'cancelled'):
        raise ValueError('Invalid status')
    with SessionLocal.begin() as db:
        return db.execute(text("""
            UPDATE website_inbound_events SET status=CAST(:status AS VARCHAR(20)), updated_at=NOW(),
                processed_at=CASE WHEN :status='processed' THEN NOW() ELSE NULL END,
                claim_token=NULL, processing_started_at=NULL, last_error=:error,
                next_retry_at=CASE WHEN :status='failed' THEN NOW() + (:delay * INTERVAL '1 second') ELSE NULL END
            WHERE id=:id AND status='processing' AND claim_token=:claim_token
        """), {**event, 'status': status, 'error': error,
               'delay': min(2 ** min(event['attempts'], 9), 300)}).rowcount == 1


def inspect_event(event):
    with SessionLocal() as db:
        row = db.execute(text("""
            SELECT m.content, c.automation_enabled, c.status, s.is_active,
                EXISTS (SELECT 1 FROM messages r WHERE r.tenant_id=e.tenant_id
                    AND r.conversation_id=e.conversation_id AND r.inbound_message_id=e.message_id
                    AND r.direction='outbound') AS confirmed
            FROM website_inbound_events e
            JOIN conversations c ON c.id=e.conversation_id AND c.tenant_id=e.tenant_id AND c.channel='website'
            JOIN website_sites s ON s.id=e.site_id AND s.tenant_id=e.tenant_id
            JOIN messages m ON m.id=e.message_id AND m.tenant_id=e.tenant_id
                AND m.conversation_id=e.conversation_id AND m.direction='inbound'
            WHERE e.id=:id AND e.claim_token=:claim_token AND e.status='processing'
                AND EXISTS (SELECT 1 FROM visitor_sessions v WHERE v.tenant_id=e.tenant_id
                    AND v.site_id=e.site_id AND v.conversation_id=e.conversation_id)
        """), event).mappings().first()
        return dict(row) if row else None


def process_event(event):
    state = inspect_event(event)
    if state is None:
        finish_event(event, 'cancelled')
        return
    if state['confirmed']:
        finish_event(event, 'processed')
        return
    if not state['automation_enabled'] or state['status'] != 'open' or not state['is_active']:
        finish_event(event, 'cancelled')
        return
    url, key = os.getenv('N8N_WEBHOOK_URL'), os.getenv('N8N_WEBHOOK_KEY')
    if not url or not key:
        raise RuntimeError('n8n configuration missing')
    payload = {k: event[k] for k in ('tenant_id', 'site_id', 'conversation_id')}
    payload.update(inbound_message_id=event['message_id'], mensaje=state['content'], canal='website')
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method='POST',
        headers={'Content-Type': 'application/json', 'X-Webhook-Key': key})
    # No database session/transaction survives across network I/O.
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError('n8n HTTP failure')
    state = inspect_event(event)
    if not state or not state['confirmed']:
        raise RuntimeError('Reply not persisted; retry required')
    finish_event(event, 'processed')


def fail_event(event, error):
    # Never persist response bodies, URLs or credentials in error logs.
    finish_event(event, 'failed', type(error).__name__)


def main():
    logging.basicConfig(level=logging.INFO)
    if os.getenv('WEBSITE_WORKER_ENABLED', 'false').lower() != 'true':
        logger.info('Website worker disabled')
        return
    while True:
        try:
            event = claim_event()
            if event is None:
                time.sleep(POLL_INTERVAL)
                continue
            try:
                process_event(event)
            except Exception as error:
                fail_event(event, error)
                logger.warning('Website event %s failed: %s', event['id'], type(error).__name__)
        except Exception as error:
            logger.warning('Worker cycle failed: %s', type(error).__name__)
            time.sleep(POLL_INTERVAL)


if __name__ == '__main__':
    main()
