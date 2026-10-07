import json
import secrets
import unittest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import select
from backend.db import Session
from backend.models import User, Customer, Restaurant, Address, Order, MenuItem, CartItem, now
from backend.delivery_fee_models import Country, CountryDeliverySettings, OrderDeliveryFeeSnapshot
from backend.delivery_fee_schemas import CountryInput, DeliverySettingsInput, SurgeInput
from backend.schemas import Checkout, CheckoutQuote
from backend.services import delivery_fee_service as service, order_service


class DeliveryFeeTests(unittest.TestCase):
    def setUp(self):
        self.db = Session()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def compute(self, code, food, distance, **kwargs):
        return service.compute(self.db, code, kwargs.pop('state', ''), kwargs.pop('city', ''), Decimal(str(food)), Decimal(str(distance)), **kwargs)

    def test_india_distance_boundaries(self):
        for distance, fee in [('0', 20), ('3', 20), ('3.0001', 30), ('5', 30), ('5.0001', 40), ('8', 40), ('8.0001', 55), ('12', 55), ('13', 60), ('12.5', 57.5)]:
            with self.subTest(distance=distance):
                result = self.compute('IN', 350, distance)
                self.assertEqual(result['total_delivery_fee'], Decimal(str(fee)))
                self.assertEqual(result['currency_code'], 'INR')

    def test_us_distance_boundaries(self):
        for miles, fee in [('0', 2.99), ('2', 2.99), ('2.0001', 4.98), ('5', 4.98), ('5.0001', 6.98), ('8', 6.98), ('8.0001', 8.98), ('12', 8.98), ('13', 9.48)]:
            with self.subTest(miles=miles):
                result = self.compute('US', 25, Decimal(miles) * Decimal('1.609344'))
                self.assertEqual(result['total_delivery_fee'], Decimal(str(fee)))
                self.assertEqual(result['service_fee'], Decimal('2.00'))

    def test_small_order_and_free_delivery_boundaries(self):
        self.assertEqual(self.compute('IN', '149.99', 3)['small_order_fee'], 10)
        self.assertEqual(self.compute('IN', 150, 3)['small_order_fee'], 0)
        self.assertEqual(self.compute('US', '9.99', 0)['small_order_fee'], 2)
        self.assertEqual(self.compute('US', 10, 0)['small_order_fee'], 0)
        self.assertEqual(self.compute('IN', 499, 5)['total_delivery_fee'], 0)
        self.assertEqual(self.compute('IN', 499, '5.0001')['total_delivery_fee'], 40)
        self.assertEqual(self.compute('US', 35, Decimal(5)*Decimal('1.609344'))['total_delivery_fee'], 0)
        self.assertEqual(self.compute('US', 35, Decimal('5.0001')*Decimal('1.609344'))['total_delivery_fee'], Decimal('6.98'))

    def test_pickup_has_no_delivery_small_or_surge_fee(self):
        result = self.compute('US', 5, 0, mode='pickup')
        self.assertEqual(result['total_delivery_fee'], 0)
        self.assertEqual(result['service_fee'], Decimal('.40'))

    def test_city_state_priority_and_disabled_location(self):
        national = self.db.scalar(select(CountryDeliverySettings).where(CountryDeliverySettings.country_code == 'US', CountryDeliverySettings.state == '', CountryDeliverySettings.city == ''))
        payload = service.settings_view(national)
        payload.update(state='Tennessee', base_fee='4')
        service.save_settings(self.db, 'US', DeliverySettingsInput(**payload))
        payload.update(city='Nashville', base_fee='5')
        service.save_settings(self.db, 'US', DeliverySettingsInput(**payload))
        self.assertEqual(self.compute('US', 25, 0, state='Tennessee', city='Nashville')['base_fee'], 5)
        self.assertEqual(self.compute('US', 25, 0, state='Tennessee', city='Franklin')['base_fee'], 4)
        self.assertEqual(self.compute('US', 25, 0, state='California', city='Oakland')['base_fee'], Decimal('2.99'))
        payload.update(active=False)
        service.save_settings(self.db, 'US', DeliverySettingsInput(**payload))
        with self.assertRaises(HTTPException):
            self.compute('US', 25, 0, state='Tennessee', city='Nashville')

    def test_timed_surges_and_most_specific_reason(self):
        service.save_surge(self.db, 'IN', SurgeInput(reason='rain', amount=10, active=True))
        service.save_surge(self.db, 'IN', SurgeInput(state='Maharashtra', city='Pune', reason='rain', amount=20, active=True))
        from datetime import timezone
        service.save_surge(self.db, 'IN', SurgeInput(reason='holiday', amount=15, active=True, ends_at=(now()-timedelta(seconds=1)).replace(tzinfo=timezone.utc)))
        result = self.compute('IN', 350, 4, state='Maharashtra', city='Pune')
        self.assertEqual(result['surge_fee'], 20)
        self.assertEqual(result['total_delivery_fee'], 50)
        self.assertEqual(self.compute('IN', 499, 4, state='Maharashtra', city='Pune')['total_delivery_fee'], 20)

    def test_country_can_be_added_without_code_changes(self):
        code = 'ZZ'
        service.save_country(self.db, CountryInput(country_code=code, country_name='Audit country', currency_code='CAD', currency_symbol='C$', distance_unit='km'))
        service.save_settings(self.db, code, DeliverySettingsInput(base_fee=3, small_order_threshold=10, small_order_fee=1, free_delivery_threshold=40, free_delivery_max_distance=5, service_fee_percent=7,
            distance_tiers=[{'up_to': 3, 'fee': 0}, {'up_to': None, 'fee': 2, 'per_unit': 1}]))
        result = self.compute(code, 20, 4)
        self.assertEqual(result['currency_code'], 'CAD')
        self.assertEqual(result['grand_total'], Decimal('27.40'))

    def test_validation_and_country_fee_limits(self):
        for tiers in [[{'up_to': 3, 'fee': 0}], [{'up_to': 5, 'fee': 1}, {'up_to': 3, 'fee': 2}, {'up_to': None, 'fee': 5}]]:
            with self.assertRaises(ValueError):
                DeliverySettingsInput(base_fee=0, small_order_threshold=0, small_order_fee=0, free_delivery_max_distance=0, distance_tiers=tiers)
        row = self.db.scalar(select(CountryDeliverySettings).where(CountryDeliverySettings.country_code == 'IN', CountryDeliverySettings.state == '', CountryDeliverySettings.city == ''))
        payload = service.settings_view(row); payload['service_fee_percent'] = 6
        with self.assertRaises(HTTPException):
            service.save_settings(self.db, 'IN', DeliverySettingsInput(**payload))

    def fixtures(self):
        customer = User(email='fee-audit-'+secrets.token_hex(8)+'@example.com', password='x', name='Fee audit customer', role='customer', country='IN')
        owner = User(email='fee-audit-'+secrets.token_hex(8)+'@example.com', password='x', name='Fee audit restaurant', role='restaurant')
        self.db.add_all([customer, owner]); self.db.flush()
        restaurant = Restaurant(id=owner.id, name='Fee audit', country='US', currency='USD', address='Audit restaurant', latitude=36.15, longitude=-86.78, is_open=True)
        self.db.add_all([Customer(id=customer.id), restaurant]); self.db.flush()
        address = Address(customer_id=customer.id, label='Audit', details='Audit US delivery address', country='US', state='Tennessee', city='Nashville', latitude=36.16, longitude=-86.77)
        menu = MenuItem(restaurant_id=owner.id, name='Audit meal', price=25)
        self.db.add_all([address, menu]);self.db.flush()
        self.db.add(CartItem(customer_id=customer.id, menu_item_id=menu.id, quantity=1)); self.db.flush()
        return customer, restaurant, address

    def test_quote_checkout_and_immutable_snapshot(self):
        customer, restaurant, address = self.fixtures()
        data = Checkout(mode='delivery', payment_mode='Cash', address_id=address.id, tip=2, request_key=secrets.token_hex(16))
        with patch('backend.services.eta_service.route', return_value={'distance_meters': 6437.376, 'distance_type': 'driving'}), patch('backend.services.dispatch_service.nearby', return_value=[]):
            preview = order_service.checkout_quote(self.db, customer, data)
            result = order_service.checkout(self.db, customer, data)
        order = self.db.get(Order, result['id'])
        self.assertEqual(order.total, preview['total'])
        self.assertEqual(preview['currency'], 'USD')
        self.assertEqual(preview['deliveryFee'], Decimal('4.98'))
        snapshot = self.db.get(OrderDeliveryFeeSnapshot, order.id)
        self.assertEqual(snapshot.country_code, 'US')
        self.assertEqual(snapshot.distance_miles, Decimal('4.0000'))
        self.assertEqual(snapshot.grand_total, order.total)
        original = snapshot.settings_snapshot
        row = self.db.scalar(select(CountryDeliverySettings).where(CountryDeliverySettings.country_code == 'US', CountryDeliverySettings.state == '', CountryDeliverySettings.city == ''))
        row.base_fee = 50;self.db.flush();self.db.expire(snapshot)
        self.assertEqual(snapshot.total_delivery_fee, Decimal('4.98'))
        self.assertEqual(snapshot.settings_snapshot, original)

    def test_address_ownership_and_cross_country_guard(self):
        customer, restaurant, address = self.fixtures()
        with self.assertRaises(HTTPException):
            order_service.checkout_quote(self.db, customer, CheckoutQuote(mode='delivery', address_id=999999999))
        address.country = 'IN';self.db.flush()
        with self.assertRaises(HTTPException):
            service.quote(self.db, customer, restaurant, Decimal(25), 'delivery', address.id)

    def test_missing_route_uses_real_coordinates_not_fixed_distance(self):
        customer, restaurant, address = self.fixtures()
        with patch('backend.services.eta_service.route', return_value={'distance_type': 'estimated', 'distance_meters': 3218.68}):
            result = service.quote(self.db, customer, restaurant, Decimal(25), 'delivery', address.id)
        self.assertEqual(result['distance_source'], 'straight_line_estimate')
        self.assertNotEqual(result['distance_miles'], Decimal('2.0000'))
        self.assertGreater(result['distance_km'], 0)


if __name__ == '__main__':
    unittest.main()
