import hashlib
import hmac
import json
import os
import time
import httpx
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from common_app.api import api_client, renew_session, APIError


def agreement_call(request, method, suffix='', data=None):
    headers = {'Cookie': ''}
    if request.session.get('role') == 'driver' and request.session.get('token'):
        renew_session(request)
        headers['Authorization'] = 'Bearer '+request.session['token']
    token = request.session.get('driver_agreement_token')
    if token: headers['X-Driver-Agreement-Token'] = token
    key = os.getenv('DRIVER_AGREEMENT_PROXY_SECRET', '')
    if key:
        peer = request.META.get('REMOTE_ADDR', '')
        address = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[-1].strip() if peer in {'127.0.0.1', '::1'} else peer
        browser = request.META.get('HTTP_USER_AGENT', '')[:1024]
        device = (request.META.get('HTTP_SEC_CH_UA_PLATFORM', '')+'; mobile='+request.META.get('HTTP_SEC_CH_UA_MOBILE', ''))[:250]
        stamp = str(int(time.time()))
        headers.update({'X-Dashvanti-Consent-Time': stamp, 'X-Dashvanti-Consent-IP': address,
            'X-Dashvanti-Consent-Browser': browser, 'X-Dashvanti-Consent-Device': device,
            'X-Dashvanti-Consent-Signature': hmac.new(key.encode(), f'{stamp}:{address}:{browser}:{device}'.encode(), hashlib.sha256).hexdigest()})
    try:
        response = api_client().request(method, settings.API_URL+'/driver/agreement'+suffix, headers=headers, json=data)
        if response.is_error:
            detail = response.json().get('detail', 'Agreement request failed')
            raise APIError(detail if isinstance(detail, str) else 'Check all acknowledgements and enter your full legal name.', response.status_code)
        return response.json()
    except (ValueError, httpx.HTTPError) as exc:
        raise APIError('Agreement service temporarily unavailable. Please try again.', 503) from exc


def consent_status(request):
    if not request.session.get('driver_agreement_token') and not (request.session.get('role') == 'driver' and request.session.get('token')):
        return {'accepted': False}
    return agreement_call(request, 'GET', '/status')


def clear_consent(request):
    for key in ('driver_agreement_token', 'driver_agreement_version', 'driver_agreement_name'):
        request.session.pop(key, None)


@never_cache
@require_http_methods(['GET', 'POST'])
def agreement(request):
    error = ''
    if request.method == 'POST':
        if request.POST.get('action') == 'decline':
            try: agreement_call(request, 'POST', '/decline')
            except APIError: pass
            request.session.flush()
            return redirect('/driver/login')
        try:
            content = agreement_call(request, 'GET')
            data = {'agreement_version': request.POST.get('agreement_version', ''), 'full_legal_name': request.POST.get('full_legal_name', ''),
                'acknowledgements': {item['key']: request.POST.get('ack_'+item['key']) == 'on' for item in content['acknowledgements']}}
            result = agreement_call(request, 'POST', '/accept', data)
            request.session['driver_agreement_version'] = result['agreement_version']
            request.session['driver_agreement_name'] = data['full_legal_name'].strip()
            messages.success(request, result['message'])
            return redirect('/driver/partner' if request.session.get('role') == 'driver' and request.session.get('token') else '/driver/register')
        except APIError as exc: error = str(exc)
    try:
        content = agreement_call(request, 'POST', '/session')
        request.session['driver_agreement_token'] = content.pop('token')
        return render(request, 'driver_app/agreement.html', {**content, 'title': content['title'], 'error': error})
    except APIError as exc:
        return render(request, 'error.html', {'error': str(exc)}, status=exc.status)


@never_cache
@require_http_methods(['POST'])
def read(request):
    try:
        data = json.loads(request.body)
        return JsonResponse(agreement_call(request, 'POST', '/read', data))
    except (ValueError, TypeError): return JsonResponse({'detail': 'Invalid agreement read event'}, status=400)
    except APIError as exc: return JsonResponse({'detail': str(exc)}, status=exc.status)
