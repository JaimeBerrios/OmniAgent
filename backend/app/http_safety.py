"""Bound request bodies, including chunked requests, before parsing JSON."""
from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes=1048576):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            part = await receive()
            if part['type'] == 'http.disconnect':
                return
            size += len(part.get('body', b''))
            if size > self.max_bytes:
                return await JSONResponse({'detail': 'Contenido demasiado grande'}, status_code=413)(scope, receive, send)
            chunks.append(part)
            if not part.get('more_body', False):
                break
        async def replay():
            if chunks:
                return chunks.pop(0)
            return await receive()
        await self.app(scope, replay, send)


class WidgetCORSMiddleware:
    """Keep error responses readable to a registered widget origin as well."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope['path'].startswith('/api/v1/widget/'):
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        origin = headers.get(b'origin', b'').decode('latin1')
        allowed = False
        if origin:
            from starlette.concurrency import run_in_threadpool
            from sqlalchemy import select
            from .database import SessionLocal
            from .models import WebsiteSite
            def registered():
                with SessionLocal() as db:
                    return db.scalar(select(WebsiteSite.id).where(WebsiteSite.origin == origin,
                            WebsiteSite.is_active.is_(True)).limit(1)) is not None
            allowed = await run_in_threadpool(registered)
        async def cors_send(message):
            if message['type'] == 'http.response.start':
                response_headers = [(k, v) for k, v in message.get('headers', [])
                                    if k.lower() not in (b'access-control-allow-origin', b'cache-control')]
                response_headers.append((b'cache-control', b'no-store'))
                if allowed:
                    response_headers.append((b'access-control-allow-origin', origin.encode('latin1')))
                    response_headers.append((b'vary', b'Origin'))
                message['headers'] = response_headers
            await send(message)
        await self.app(scope, receive, cors_send)
