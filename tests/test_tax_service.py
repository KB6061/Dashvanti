from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from backend.services.tax_service import calculate_order_tax

def test_dynamic_order_tax_uses_rate():
    items = [
        SimpleNamespace(price=Decimal('10.00'), quantity=2, category='food'),
        SimpleNamespace(price=Decimal('3.00'), quantity=1, category='beverage'),
    ]
    with patch('backend.services.tax_service.get_us_tax_rate', return_value=Decimal('0.0925')):
        result = calculate_order_tax(items, '37067', Decimal('3.00'), Decimal('1.00'))
    assert result == {
        'tax_rate': Decimal('0.0925'),
        'subtotal': Decimal('23.00'),
        'item_tax_total': Decimal('2.13'),
        'delivery_fee': Decimal('3.00'),
        'delivery_tax': Decimal('0.28'),
        'platform_fee': Decimal('1.00'),
        'platform_tax': Decimal('0.09'),
        'grand_total': Decimal('29.50'),
    }
