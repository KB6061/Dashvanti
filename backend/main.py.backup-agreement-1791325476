from backend.routers import presence
from backend.request_logging import RequestLoggingMiddleware
from backend.routers import social_auth
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
app.include_router(social_auth.router, prefix='/api')
app.include_router(api.router, prefix='/api')
app.include_router(tax.router, prefix='/api')
app.include_router(operations.router, prefix='/api')

@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse(status_code=409, content={'detail':'This operation conflicts with an existing record'})

@app.get('/api/')
@app.get('/health')
def health():
    with engine.connect() as connection:
        connection.execute(text('SELECT 1'))
    return {'status':'ok'}

from backend.routers import phonepe, admin_payment
app.include_router(phonepe.router, prefix='/api')
app.include_router(admin_payment.router, prefix='/api')
from backend.routers import gps_ticket
app.include_router(gps_ticket.router,prefix='/api')
from backend.routers.order_update import router as order_update_router
from backend.services.order_broadcast_service import install as install_order_broadcast
install_order_broadcast()
from backend.routers.restaurant_experience import router as restaurant_experience_router
app.include_router(restaurant_experience_router, prefix='/api')
app.include_router(order_update_router,prefix='/api')

from backend.routers import customer_push_router
app.include_router(customer_push_router.router, prefix="/api")

from backend.routers import driver_partner
app.include_router(driver_partner.router, prefix='/api')
