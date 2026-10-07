from django.http import HttpResponseForbidden, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.contrib import messages
from common_app.api import call, APIError
from common_app.account_experience import proxy
from django.views.decorators.http import require_http_methods
from datetime import datetime, timezone


@require_http_methods(['GET', 'POST'])
def account_login(request):
    error = ''
    if request.method == 'POST':
        try:
            result = call(request, 'POST', '/account-experience/admin/sign-in', {
                'email': request.POST.get('email', ''),
                'password': request.POST.get('password', ''), 'role': 'admin'})
            if result.get('role') != 'admin' or not result.get('access_token'):
                raise APIError('Admin authentication required', 403)
            request.session.cycle_key()
            request.session['token'] = result['access_token']
            request.session['refresh_token'] = result['refresh_token']
            request.session['role'] = 'admin'
            request.session['admin_authenticated'] = True
            identity = call(request, 'GET', '/account-experience/identity')
            request.session['name'] = identity.get('name', '')
            request.session['user_id'] = identity['id']
            request.session['admin_login_at'] = datetime.now(timezone.utc).isoformat()
            return redirect('/admin/support-center')
        except APIError as exc:
            error = str(exc)
    return render(request, 'admin_app/account_login.html', {'account_error': error, 'title': 'Admin Account Sign In'})


def allowed(request):
    return request.session.get('role') == 'admin' and request.session.get('token')


def experience_proxy(request, endpoint):
    if not allowed(request):
        return HttpResponseForbidden()
    return proxy(request, endpoint)


def support_center(request):
    if not allowed(request):
        return redirect('/admin/account-login')
    error=''
    if request.method=='POST':
        try:
            call(request,'POST','/account-experience/admin/support-sla',{'priority':request.POST['priority'],'minutes':int(request.POST['minutes']),'reason':request.POST.get('reason','')})
            messages.success(request,'SLA policy saved for new tickets')
            return redirect(request.path)
        except (APIError,ValueError,KeyError) as exc:error=str(exc)
    filters = {key: value for key, value in request.GET.items() if key in {'q','status','priority','category','assignee_id','date_from','date_to','sort','direction','page','size'} and value}
    result = call(request, 'GET', '/account-experience/tickets', params=filters)
    context = {'incidents': result, 'ticket_filters': filters, 'incident_admin': True,
               'tickets_has_next': result['page']*result['size'] < result['total'],
               'ticket_statuses': ['Open','Assigned','In Progress','Waiting Customer','Escalated','Resolved','Closed'], 'title': 'Support Center','account_error':error,'sla_policies':call(request,'GET','/account-experience/admin/support-sla')}
    if request.headers.get('X-Incident-Panel') == '1':
        return JsonResponse({'html': render_to_string('account_components/ticket_list.html', context, request=request)})
    return render(request, 'admin_app/account_support.html', context)


def audit_center(request):
    if not allowed(request):
        return redirect('/admin/account-login')
    error = ''
    if request.method == 'POST':
        try:
            call(request, 'POST', '/account-experience/admin/audit/' + str(int(request.POST['audit_id'])) + '/rollback', {'reason': request.POST.get('reason', '')})
            messages.success(request, 'Previous values restored')
            return redirect('/admin/audit-center')
        except (APIError, ValueError, KeyError) as exc:
            error = str(exc)
    filters = {key: value for key, value in request.GET.items() if key in {'q','admin_id','module','action','status','date_from','date_to','page','size','export'} and value}
    if filters.get('export'):
        result = call(request, 'GET', '/account-experience/admin/audit', params=filters, raw=True)
        response = HttpResponse(result.content, content_type='application/json')
        response['Content-Disposition'] = 'attachment; filename="dashvanti-admin-audit.json"'
        response['Cache-Control'] = 'no-store'
        return response
    audit = call(request, 'GET', '/account-experience/admin/audit', params=filters)
    return render(request, 'admin_app/account_audit.html', {'audit': audit, 'filters': filters, 'account_error': error,
                  'assignees': call(request, 'GET', '/account-experience/admin/assignees'),
                  'has_next': audit['page']*audit['size'] < audit['total'], 'title': 'Audit Center'})


def gateway_controls(request):
    if not allowed(request):
        return redirect('/admin/account-login')
    error = ''
    if request.method == 'POST':
        try:
            if request.POST.get('region_kind'):
                call(request,'POST','/account-experience/admin/regions/'+request.POST['region_kind'],{'id':int(request.POST['id']),'country':request.POST['country'],'city':request.POST.get('city',''),'state':request.POST.get('state',''),'reason':request.POST.get('reason','')})
            else:
                call(request, 'POST', '/account-experience/admin/gateways', {'name': request.POST.get('name'), 'enabled': request.POST.get('enabled') == 'on', 'countries': request.POST.getlist('countries'), 'reason': request.POST.get('reason','')})
            messages.success(request, 'Gateway visibility saved')
            return redirect(request.path)
        except (APIError,ValueError,KeyError) as exc:
            error = str(exc)
    return render(request, 'admin_app/account_gateways.html', {'data': call(request, 'GET', '/account-experience/admin/gateways'), 'account_error': error, 'title': 'Gateway Controls'})


def review_moderation(request):
    if not allowed(request):
        return redirect('/admin/account-login')
    error = ''
    if request.method == 'POST':
        try:
            call(request, 'POST', '/account-experience/reviews/' + str(int(request.POST['review_id'])), {'action': request.POST.get('action'), 'reason': request.POST.get('reason','')})
            messages.success(request, 'Review moderation saved')
            return redirect(request.path)
        except (APIError, ValueError, KeyError) as exc:
            error = str(exc)
    return render(request, 'admin_app/account_reviews.html', {'data': call(request, 'GET', '/account-experience/admin/reviews', params={key:value for key,value in request.GET.items() if key in {'page','size'}}), 'account_error': error, 'title': 'Review Moderation'})


def account_verification(request):
    if not allowed(request):
        return redirect('/admin/account-login')
    error = ''
    if request.method == 'POST':
        try:
            call(request, 'POST', '/account-experience/admin/verification', {'user_id': int(request.POST['user_id']), 'verified': request.POST.get('verified') == 'on', 'reason': request.POST.get('reason','')})
            messages.success(request, 'Verification saved')
            return redirect(request.path)
        except (APIError,ValueError,KeyError) as exc:
            error = str(exc)
    return render(request, 'admin_app/account_verification.html', {'account_error': error, 'title': 'Account Verification'})


@require_http_methods(['GET','POST'])
def wallet_refunds(request):
    if not allowed(request):return redirect('/admin/account-login')
    error=''
    if request.method=='POST':
        try:
            result=call(request,'POST','/account-experience/admin/wallet-refunds',{'refund_id':request.POST.get('refund_id',''),'reason':request.POST.get('reason','')})
            messages.success(request,result['message'])
            return redirect(request.path)
        except APIError as exc:error=str(exc)
    result=call(request,'GET','/operations/funds')
    return render(request,'admin_app/wallet_refunds.html',{'refunds':result['refunds'],'account_error':error,'title':'Wallet Refund Credits'})
