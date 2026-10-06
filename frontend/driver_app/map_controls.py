from pathlib import Path
from django.http import FileResponse
from django.views.decorators.http import require_GET
from common_app.road_controls import road_controls

@require_GET
def notifications_worker(request):
 from driver_app.partner_views import push_worker
 return push_worker(request)
 response=FileResponse((Path(__file__).resolve().parents[1]/'static/driver-notifications-worker.js').open('rb'),content_type='application/javascript')
 response['Cache-Control']='no-cache'
 response['Service-Worker-Allowed']='/driver/'
 return response

