from pathlib import Path
from django.conf import settings
from django.http import FileResponse
from django.views.decorators.http import require_GET


@require_GET
def arrival(request):
    response = FileResponse((settings.BASE_DIR / 'static/sounds/arrival.mp3').open('rb'), content_type='audio/mpeg')
    response['Cache-Control'] = 'public, max-age=86400'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
