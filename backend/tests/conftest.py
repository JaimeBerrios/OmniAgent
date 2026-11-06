import os
os.environ.setdefault('DATABASE_URL', os.environ.get('OMNI_TEST_DATABASE_URL', 'postgresql+psycopg://test:test@localhost/test'))
os.environ.setdefault('JWT_SECRET_KEY', 'local-tests-only-key-at-least-32-characters')
os.environ.setdefault('WHATSAPP_TENANT_ID', '1')
os.environ.setdefault('WHATSAPP_PHONE_NUMBER_ID', '1')
