"""Seed browser credentials exclusively in the disposable omni_test database."""
import json
import os
import secrets
from pathlib import Path
from app.database import SessionLocal
from app.models import Tenant, User, Membership, WebsiteSite
from app.security import hash_password

if not os.environ.get('OMNI_TEST_DATABASE_URL', '').endswith('/omni_test'):
    raise SystemExit('OMNI_TEST_DATABASE_URL must point to disposable omni_test')
if os.environ['DATABASE_URL'] != os.environ['OMNI_TEST_DATABASE_URL']:
    raise SystemExit('DATABASE_URL must match OMNI_TEST_DATABASE_URL')
password = secrets.token_urlsafe(24)
with SessionLocal.begin() as db:
    tenant = Tenant(name='Browser test')
    user = User(email=secrets.token_hex(12)+'@browser.invalid',password_hash=hash_password(password))
    db.add_all([tenant,user]);db.flush()
    db.add(Membership(tenant_id=tenant.id,user_id=user.id,role='owner'))
    site = WebsiteSite(tenant_id=tenant.id,public_id=secrets.token_urlsafe(24),name='Browser test',origin='https://browser-test.example')
    db.add(site);db.flush()
    fixture = {'email':user.email,'password':password,'site':site.public_id}
path = Path(os.environ.get('OMNI_BROWSER_FIXTURE','/tmp/omni-browser-fixture.json'))
# Restrict local test credentials to the current user.
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as stream:
    json.dump(fixture,stream)
print('Disposable browser fixture created')
