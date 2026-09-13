from fastapi import APIRouter, Depends
from backend.db import get_db
from backend.security import current_user
from backend.tax_schemas import OrderTaxCalculation
from backend.services.tax_service import calculate_tax_for_menu_items

router = APIRouter(tags=['tax'])

@router.post('/orders/calculate-tax')
def calculate_tax(data: OrderTaxCalculation, user=Depends(current_user), db=Depends(get_db, scope='function')):
    return calculate_tax_for_menu_items(db, data.items, data.customer_zip, data.delivery_fee, data.platform_fee)
