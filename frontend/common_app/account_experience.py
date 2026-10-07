import json
import re
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from common_app.api import call, APIError

ENDPOINT = re.compile(r'^(?:identity|states/(?:US|IN)|location|favorites|gateways|avatar/\d+|review-photo/\d+|reviews(?:/\d+)?|tickets(?:/\d+(?:/attachments)?)?|attachments/\d+|wallet/(?:funding(?:/[a-f0-9]{32}/verify)?|transfer)|admin/(?:regions/(?:restaurant|promotion)|gateways|assignees|reviews|verification|audit(?:/\d+(?:/rollback)?)?))$')


def proxy(request, endpoint):
    public=request.method=='GET' and (endpoint=='reviews' or endpoint.startswith(('avatar/','review-photo/','states/')))
    if not public and not request.session.get('token'):
        return JsonResponse({'error': 'Sign in again'}, status=401)
    if not ENDPOINT.fullmatch(endpoint):
        return HttpResponse(status=404)
    if request.method not in {'GET', 'POST'}:
        return HttpResponse(status=405)
    try:
        files = None
        if request.FILES:
            file = request.FILES.get('file')
            if not file:
                return JsonResponse({'error': 'Choose an attachment'}, status=422)
            files = {'file': (file.name, file, file.content_type)}
            data = {'internal': request.POST.get('internal', 'false')}
        else:
            data = json.loads(request.body) if request.method == 'POST' else None
        response = call(request, request.method, '/account-experience/' + endpoint, data,
                        params=request.GET.dict(), files=files, raw=True)
        content_type = response.headers.get('content-type', 'application/json')
        result = HttpResponse(response.content, content_type=content_type, status=response.status_code)
        for header in ('Content-Disposition', 'X-Content-Type-Options'):
            if header in response.headers:
                result[header] = response.headers[header]
        result['Cache-Control'] = 'private, no-store'
        return result
    except APIError as exc:
        return JsonResponse({'error': str(exc)}, status=exc.status)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid request'}, status=422)
