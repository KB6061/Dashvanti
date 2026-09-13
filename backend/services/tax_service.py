from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException
from sqlalchemy import select

from backend.models import MenuItem
from backend.services.tax_api_client import get_us_tax_rate

CENT = Decimal('0.01')
CATEGORIES = {'food', 'beverage', 'alcohol', 'packaged'}

def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)

def calculate_item_tax(item_price: Decimal, tax_rate: Decimal) -> Decimal:
    return money(item_price * tax_rate)

def calculate_delivery_tax(delivery_fee: Decimal, tax_rate: Decimal) -> Decimal:
    return money(delivery_fee * tax_rate)

def calculate_platform_tax(platform_fee: Decimal, tax_rate: Decimal) -> Decimal:
    return money(platform_fee * tax_rate)

def calculate_order_tax(order_items, customer_zip: str, delivery_fee: Decimal, platform_fee: Decimal) -> dict:
    rate = get_us_tax_rate(customer_zip)
    subtotal = sum((money(item.price) * item.quantity for item in order_items), Decimal('0.00'))
    item_tax_total = sum((calculate_item_tax(money(item.price) * item.quantity, rate) for item in order_items), Decimal('0.00'))
    delivery_fee = money(delivery_fee)
    platform_fee = money(platform_fee)
    delivery_tax = calculate_delivery_tax(delivery_fee, rate)
    platform_tax = calculate_platform_tax(platform_fee, rate)
    return {
        'tax_rate': rate,
        'subtotal': money(subtotal),
        'item_tax_total': money(item_tax_total),
        'delivery_fee': delivery_fee,
        'delivery_tax': delivery_tax,
        'platform_fee': platform_fee,
        'platform_tax': platform_tax,
        'grand_total': money(subtotal + item_tax_total + delivery_fee + delivery_tax + platform_fee + platform_tax),
    }

def calculate_tax_for_menu_items(db, items, customer_zip: str, delivery_fee: Decimal, platform_fee: Decimal) -> dict:
    quantities = {}
    for item in items:
        quantities[item.id] = quantities.get(item.id, 0) + item.quantity
    menu_items = list(db.scalars(select(MenuItem).where(MenuItem.id.in_(quantities))))
    if len(menu_items) != len(quantities):
        raise HTTPException(404, 'One or more menu items were not found')
    order_items = []
    for item in menu_items:
        category = (item.category or 'food').strip().lower()
        if category not in CATEGORIES:
            category = 'food'
        order_items.append(type('TaxItem', (), {'price': item.price, 'quantity': quantities[item.id], 'category': category})())
    return calculate_order_tax(order_items, customer_zip, delivery_fee, platform_fee)
