import sys
from contextvars import ContextVar
from django.conf import settings
from django.shortcuts import redirect
from common_app.api import renew_session, APIError

current_request=ContextVar('dashvanti_admin_request',default=None)


class AdminAuditMiddleware:
    def __init__(self,get_response):
        self.get_response=get_response

    def __call__(self,request):
        if not request.path.startswith('/admin/') or request.path in {'/admin/login','/admin/account-login','/admin/driver-partners/manager-login'}:
            return self.get_response(request)
        if request.session.get('driver_manager_token') and not request.session.get('admin_authenticated'):
            return self.get_response(request)
        if request.session.get('role')!='admin' or not request.session.get('token'):
            return redirect('/admin/login')
        sys.path.insert(0,str(settings.BASE_DIR.parent)) if str(settings.BASE_DIR.parent) not in sys.path else None
        import jwt
        from backend.config import settings as backend_settings
        from backend.db import Session
        from backend.models import User
        from backend.audit_context import actor
        from backend.services.enterprise_audit_service import install, record
        install()
        try:
            renew_session(request)
            claims=jwt.decode(request.session['token'],backend_settings.jwt_secret,algorithms=['HS256'],audience='dashvanti',issuer='dashvanti-api',options={'require':['sub','ver','exp','iat']})
            with Session() as db:
                user=db.get(User,int(claims['sub']))
                if not user or user.role!='admin' or user.token_version!=claims['ver']:raise ValueError()
                from common_app.logging_support import client_ip
                identity={'id':user.id,'name':user.name,'role':user.role,'ip':client_ip(request.META.get('REMOTE_ADDR',''),request.META.get('HTTP_X_FORWARDED_FOR','')),'device':request.META.get('HTTP_USER_AGENT','')[:500], 'reason':request.POST.get('reason','')[:500]}
        except (APIError,jwt.PyJWTError,ValueError,KeyError):
            request.session.flush()
            return redirect('/admin/login')
        request_token=current_request.set(request)
        actor_token=actor.set(identity)
        status=500
        try:
            response=self.get_response(request)
            status=response.status_code
            return response
        finally:
            try:
                with Session() as db:
                    db.info.pop('audit_actor',None)
                    record(db,identity,request.method,'portal_request',{'path':request.path},{},{'http_status':status},status='success' if status<400 else 'failed')
                    db.commit()
            finally:
                actor.reset(actor_token)
                current_request.reset(request_token)
