import io
from types import SimpleNamespace
from unittest.mock import MagicMock
import httpx
from PIL import Image
from backend.services import file_service

def test_menu_upload_prepares_thumbnail(tmp_path, monkeypatch):
    monkeypatch.setattr(file_service.settings, 'file_root', str(tmp_path))
    data = io.BytesIO()
    Image.new('RGB', (1600, 1200), 'orange').save(data, format='JPEG')
    data.seek(0)
    db = MagicMock()
    db.get.return_value = SimpleNamespace(restaurant_id=1)
    file_service.upload(db, SimpleNamespace(id=1, role='restaurant'),
                        SimpleNamespace(file=data), 'menu', 5)
    thumbs = list(tmp_path.rglob('*.thumb320.jpg'))
    assert len(thumbs) == 1
    with Image.open(thumbs[0]) as image:
        assert max(image.size) <= 320

def test_pooled_api_keeps_user_credentials_separate(monkeypatch):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'frontend'))
    from common_app import api
    from django.conf import settings
    if not settings.configured:
        settings.configure(API_URL='http://backend/api')
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={'ok': True}, headers={'set-cookie':'private=other-user'})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        monkeypatch.setattr(api, 'api_client', lambda: client)
        for token in ('first', 'second'):
            assert api.call(SimpleNamespace(session={'token':token}), 'GET', '/files/1') == {'ok':True}
    assert requests[0].headers['authorization'] == 'Bearer first'
    assert requests[1].headers['authorization'] == 'Bearer second'
    assert not requests[1].headers.get('cookie')
