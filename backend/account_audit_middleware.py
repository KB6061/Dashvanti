from backend.db import Session
from backend.services.enterprise_audit_service import record


class AccountAuditMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        status = 500

        async def capture(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            actor = scope.get('state', {}).get('audit_actor')
            if actor and actor.get('role') == 'admin':
                # Separate request audit includes failed attempts; mutation versions are transactional.
                with Session() as db:
                    record(db, actor, scope['method'], 'request', {'path': scope['path']}, {},
                           {'http_status': status}, status='success' if status < 400 else 'failed')
                    db.commit()
