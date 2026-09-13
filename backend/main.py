from backend.routers import presence
from backend.request_logging import RequestLoggingMiddleware
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from backend.db import engine
from backend.routers import auth, api, operations, funds, reports, tracking, cancellation, tax

app = FastAPI(title='Dashvanti API', version='1.0.0', docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(RequestLoggingMiddleware)
app.include_router(presence.router, prefix='/api')
app.include_router(cancellation.router, prefix='/api')
app.include_router(tracking.router, prefix='/api')
app.include_router(reports.router, prefix='/api')
app.include_router(funds.router, prefix='/api')
app.include_router(auth.router, prefix='/api')
app.include_router(api.router, prefix='/api')
app.include_router(tax.router, prefix='/api')
app.include_router(operations.router, prefix='/api')

@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse(status_code=409, content={'detail':'This operation conflicts with an existing record'})

@app.get('/health')
def health():
    with engine.connect() as connection:
        connection.execute(text('SELECT 1 FROM DUAL'))
    return {'status':'ok'}
