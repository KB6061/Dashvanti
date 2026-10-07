import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from backend.services.customer_queue_tracking_service import state

class CustomerQueueTrackingTests(unittest.TestCase):
    def check_phase(self, queued, stage, phase):
        db = Mock()
        db.scalar.side_effect = [NS(driver_id=7)] if queued else [None, 1]
        db.get.side_effect = [NS(online=True, vehicle_type='Car', vehicle_number='ABC'), NS(name='Driver', phone='123')]
        order = NS(id=2, status='ACCEPTED', mode='delivery', driver_id=None if queued else 7)
        with patch('backend.services.customer_queue_tracking_service.active_orders', return_value=[NS(id=1)]), patch('backend.services.tracking_service.states', return_value=('READY_FOR_PICKUP', stage, [])):
            result = state(db, order)
        self.assertEqual(result['phase'], phase)
        self.assertEqual(result['queued'], queued)
        self.assertNotIn('current_order_id', result)
        self.assertNotIn('address', result)

    def test_existing_pickup(self):
        self.check_phase(True, 'ARRIVED_AT_RESTAURANT', 'picking_up_other_order')

    def test_existing_delivery(self):
        self.check_phase(True, 'ON_THE_WAY_TO_CUSTOMER', 'delivering_other_orders')

    def test_existing_picked_up(self):
        self.check_phase(True, 'PICKED_UP', 'delivering_other_orders')

    def test_promoted_pickup(self):
        self.check_phase(False, 'DRIVER_ASSIGNED', 'heading_to_pickup')

    def test_new_delivery(self):
        self.check_phase(False, 'PICKED_UP', 'heading_to_customer')

    def test_final_order(self):
        db=Mock()
        self.assertIsNone(state(db, NS(status='DELIVERED', mode='delivery')))
        db.scalar.assert_not_called()

class QueueDatabaseTests(unittest.TestCase):
    from backend.tests.test_assignment_tracking import AssignmentTrackingTests as Fixture
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown

    def test_queue_phase_broadcast_and_promotion(self):
        import secrets
        from decimal import Decimal
        from sqlalchemy import select
        from backend.models import Order, DeliveryStatus
        from backend.models_order_stream import OrderBroadcastEvent
        from backend.models_driver_queue import DriverUpcomingOrder
        from backend.services import delivery_service, driver_queue_service, order_broadcast_service
        self.order.driver_id = self.driver.id
        upcoming = Order(customer_id=self.customer.id, restaurant_id=self.owner.id, request_key=secrets.token_hex(16), mode='delivery', payment_mode='Cash', status='ACCEPTED', address='Upcoming address', total=Decimal(20))
        self.db.add(upcoming);self.db.flush()
        with patch('backend.services.dispatch_service.eligible', return_value={'distance_miles':1}), patch('backend.services.driver_offer_service.validate_accept'):
            accepted = delivery_service.accept(self.db, self.driver, upcoming.id)
        self.assertTrue(accepted['queued'])
        self.assertEqual(state(self.db, upcoming)['phase'], 'picking_up_other_order')
        self.order.status = 'ON_THE_WAY_TO_CUSTOMER'
        self.db.add(DeliveryStatus(order_id=self.order.id, status='ON_THE_WAY_TO_CUSTOMER'))
        order_broadcast_service.install()
        self.db.dispatch.before_commit(self.db)
        events = list(self.db.scalars(select(OrderBroadcastEvent).where(OrderBroadcastEvent.order_id == upcoming.id)))
        self.assertTrue(any(row.payload['queue']['phase'] == 'delivering_other_orders' for row in events))
        self.order.status = 'DELIVERED';self.db.flush()
        driver_queue_service.promote(self.db, self.driver.id);self.db.flush()
        self.assertIsNone(self.db.scalar(select(DriverUpcomingOrder).where(DriverUpcomingOrder.order_id == upcoming.id)))
        self.assertEqual(upcoming.driver_id, self.driver.id)
        self.assertEqual(state(self.db, upcoming)['phase'], 'heading_to_pickup')
        upcoming.status = 'PICKED_UP'
        self.assertEqual(state(self.db, upcoming)['phase'], 'heading_to_customer')
