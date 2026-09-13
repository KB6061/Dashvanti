import pytest
from fastapi.testclient import TestClient
from backend.docs import app, settings

@pytest.fixture
def docs_client(monkeypatch):
    monkeypatch.setattr(settings, 'admin_secret', 'docs-test-password')
    with TestClient(app) as client:
        yield client

def test_docs_require_admin(docs_client):
    for path in ('/docs', '/openapi.json'):
        response = docs_client.get(path)
        assert response.status_code == 401
        assert response.headers['www-authenticate'].startswith('Basic')

def test_wrong_credentials_rejected(docs_client):
    assert docs_client.get('/docs', auth=('admin', 'wrong')).status_code == 401
    assert docs_client.get('/docs', auth=('driver', 'docs-test-password')).status_code == 401

def test_docs_and_schema(docs_client):
    auth = ('admin', 'docs-test-password')
    response = docs_client.get('/docs', auth=auth)
    assert response.status_code == 200
    assert 'SwaggerUIBundle' in response.text
    assert 'displayRequestDuration' in response.text
    assert response.headers['cache-control'] == 'no-store'
    schema = docs_client.get('/openapi.json', auth=auth).json()
    assert '/api/auth/login' in schema['paths']
    assert '/health' in schema['paths']
    assert '/docs' not in schema['paths']
    assert schema['servers'] == [{'url': '/'}]
    assert 'docs-test-password' not in str(schema)

def test_docs_login_does_not_grant_api_access(docs_client):
    response = docs_client.get('/api/me', auth=('admin', 'docs-test-password'))
    assert response.status_code in (401, 403)

def test_root_opens_docs(docs_client):
    response = docs_client.get('/', follow_redirects=False)
    assert response.status_code == 307
    assert response.headers['location'] == '/docs'
