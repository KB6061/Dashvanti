import secrets
from fastapi import Depends, HTTPException
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from backend.config import settings
from backend.main import app

basic = HTTPBasic(auto_error=False)

def docs_admin(credentials: HTTPBasicCredentials = Depends(basic)):
    if not credentials or not settings.admin_secret:
        raise HTTPException(401, 'Admin login required', headers={'WWW-Authenticate': 'Basic realm="Dashvanti API"'})
    valid_user = secrets.compare_digest(credentials.username.encode(), b'admin')
    valid_password = secrets.compare_digest(credentials.password.encode(), settings.admin_secret.encode())
    if not (valid_user and valid_password):
        raise HTTPException(401, 'Invalid admin login', headers={'WWW-Authenticate': 'Basic realm="Dashvanti API"'})

@app.get('/', include_in_schema=False)
def index():
    return RedirectResponse('/docs')

@app.get('/docs', include_in_schema=False, dependencies=[Depends(docs_admin)])
def documentation():
    response = get_swagger_ui_html(
        openapi_url='/openapi.json',
        title='Dashvanti API Portal',
        swagger_ui_parameters={
            'filter': True,
            'docExpansion': 'none',
            'displayRequestDuration': True,
            'persistAuthorization': False,
            'tryItOutEnabled': True,
            'defaultModelsExpandDepth': 0,
        },
    )
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.get('/openapi.json', include_in_schema=False, dependencies=[Depends(docs_admin)])
def schema():
    document = dict(app.openapi())
    document['servers'] = [{'url': '/'}]
    document['info'] = {
        **document['info'],
        'description': (
            'Live Dashvanti API. Expand an endpoint to view its request schema. '
            'Use Execute to see the response body, HTTP status, headers, and duration. '
            'Requests affect the live application. For role endpoints, obtain an access_token '
            'from /api/auth/login and enter it using Authorize. Admin endpoints require '
            'the X-Dashvanti-Admin-Secret field. Documentation login does not bypass API authorization.'
        ),
    }
    return JSONResponse(document, headers={'Cache-Control': 'no-store'})
