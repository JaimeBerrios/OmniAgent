"""Shared fixed-window limits in PostgreSQL, independent of API process count."""
import hashlib
from sqlalchemy import text
from fastapi import HTTPException


def consume(db, key, limit):
    # Separate transaction: a rejected or rolled-back request still consumes quota.
    from .database import engine
    with engine.begin() as connection:
        count = connection.execute(text('''
            INSERT INTO request_limits (key, window_start, count)
            VALUES (:key, date_trunc('minute', NOW()), 1)
            ON CONFLICT (key) DO UPDATE SET
                count = CASE WHEN request_limits.window_start = EXCLUDED.window_start
                             THEN request_limits.count + 1 ELSE 1 END,
                window_start = EXCLUDED.window_start
            RETURNING count
        '''), {'key': hashlib.sha256(key.encode()).hexdigest()}).scalar_one()
    if count > limit:
        raise HTTPException(429, 'Demasiadas solicitudes; espera un minuto', headers={'Retry-After': '60'})
