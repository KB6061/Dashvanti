import unittest
import uuid
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import select, func
from backend.db import Session
from backend.models import User, Customer, Restaurant, MenuItem, CartItem, Order, Review, Rating, DeliveryStatus, File
from backend.schemas import CartInput, Checkout, ReviewInput
from backend.services import order_service
from backend.services import restaurant_experience_service as service
from backend.restaurant_experience_models import ScheduledOrder, GroupOrder, GroupMember, GroupItem

class RestaurantExperienceTest(unittest.TestCase):
    def setUp(self):
        self.db = Session()
        self.addCleanup(self.db.close)
        self.addCleanup(self.db.rollback)
        def user(role):
            row = User(email=f'experience-audit-{uuid.uuid4()}@example.com', name='Experience integration audit', password='disabled-test-account', role=role)
            self.db.add(row); self.db.flush()
            if role == 'customer':
                self.db.add(Customer(id=row.id)); self.db.flush()
            return row
        self.host, self.member, self.outsider = user('customer'), user('customer'), user('customer')
        owner = user('restaurant')
        self.store = Restaurant(id=owner.id, name='Transactional test restaurant', opening='00:00', closing='23:59', is_open=False, country='US', latitude=36.16, longitude=-86.78, currency='USD')
        self.db.add(self.store); self.db.flush()
        self.item = MenuItem(restaurant_id=self.store.id, name='Transactional test menu', category='Lunch', price=10, available=True)
        self.db.add(self.item); self.db.flush()

    def test_shared_cart_membership_quantity_and_host_checkout(self):
        group = service.create_group(self.db, self.host, self.store.id)
        with self.assertRaises(HTTPException) as error:
            service.group_data(self.db, self.outsider, group['id'])
        self.assertEqual(404, error.exception.status_code)
        joined = service.join_group(self.db, self.member, group['invite_code'])
        self.assertFalse(joined['host'])
        service.change_group(self.db, self.host, group['id'], self.item.id, 2)
        service.change_group(self.db, self.member, group['id'], self.item.id, 1)
        with self.assertRaises(HTTPException) as error:
            service.finish_group(self.db, self.member, group['id'])
        self.assertEqual(403, error.exception.status_code)
        service.finish_group(self.db, self.host, group['id'])
        service.finish_group(self.db, self.host, group['id'])
        cart = self.db.scalar(select(CartItem).where(CartItem.customer_id == self.host.id))
        self.assertEqual(3, cart.quantity)
        with self.assertRaises(HTTPException):
            service.change_group(self.db, self.member, group['id'], self.item.id, 2)

    def test_host_removes_group_and_all_shared_records(self):
        group = service.create_group(self.db, self.host, self.store.id)
        service.join_group(self.db, self.member, group['invite_code'])
        service.change_group(self.db, self.member, group['id'], self.item.id, 2)
        service.remove_group(self.db, self.host, group['id'])
        self.assertIsNone(self.db.get(GroupOrder, group['id']))
        for model in (GroupMember, GroupItem):
            self.assertEqual(0, self.db.scalar(select(func.count()).select_from(model).where(model.group_id == group['id'])))
        self.assertIsNone(service.experience(self.db, self.store.id, self.member)['active_group'])

    def test_repeated_start_reuses_existing_group(self):
        first = service.create_group(self.db, self.host, self.store.id)
        second = service.create_group(self.db, self.host, self.store.id)
        self.assertEqual(first['id'], second['id'])

    def test_member_leaves_without_removing_host_items(self):
        group = service.create_group(self.db, self.host, self.store.id)
        service.join_group(self.db, self.member, group['invite_code'])
        service.change_group(self.db, self.host, group['id'], self.item.id, 1)
        service.change_group(self.db, self.member, group['id'], self.item.id, 2)
        service.remove_group(self.db, self.member, group['id'])
        result = service.group_data(self.db, self.host, group['id'])
        self.assertEqual(1, len(result['members']))
        self.assertEqual(1, result['items'][0]['quantity'])
        with self.assertRaises(HTTPException):
            service.group_data(self.db, self.member, group['id'])

    def test_outsider_and_checked_out_groups_cannot_be_removed(self):
        group = service.create_group(self.db, self.host, self.store.id)
        with self.assertRaises(HTTPException) as denied:
            service.remove_group(self.db, self.outsider, group['id'])
        self.assertEqual(404, denied.exception.status_code)
        service.change_group(self.db, self.host, group['id'], self.item.id, 1)
        service.finish_group(self.db, self.host, group['id'])
        with self.assertRaises(HTTPException) as denied:
            service.remove_group(self.db, self.host, group['id'])
        self.assertEqual(409, denied.exception.status_code)

    def scheduled_order(self):
        slot = service.slots(self.store)[2]['value']
        service.set_plan(self.db, self.host, self.store.id, slot)
        order_service.update_cart(self.db, self.host, CartInput(menu_item_id=self.item.id, quantity=1))
        result = order_service.checkout(self.db, self.host, Checkout(mode='pickup', request_key=uuid.uuid4().hex))
        return self.db.get(Order, result['id'])

    def test_schedule_is_stored_and_released_once(self):
        order = self.scheduled_order()
        self.assertEqual('SCHEDULED', order.status)
        schedule = self.db.get(ScheduledOrder, order.id)
        self.assertIsNotNone(schedule)
        schedule.release_at = datetime.utcnow() - timedelta(seconds=1)
        self.store.is_open = True; self.db.flush()
        service.release_due(self.db, [order.id]); service.release_due(self.db, [order.id])
        self.assertEqual('PLACED', order.status)
        count = self.db.scalar(select(func.count(DeliveryStatus.id)).where(DeliveryStatus.order_id == order.id, DeliveryStatus.status == 'PLACED'))
        self.assertEqual(1, count)

    def test_review_count_rating_and_completed_order_ownership(self):
        order = self.scheduled_order()
        order.status = 'DELIVERED'; self.db.flush()
        before = service.experience(self.db, self.store.id, self.host)
        self.assertIn(order.id, before['eligible_order_ids'])
        order_service.review(self.db, self.host, order.id, ReviewInput(restaurant=4, text='Real contract test review'))
        self.db.flush()
        after = service.experience(self.db, self.store.id, self.host)
        self.assertEqual(1, after['rating_count'])
        self.assertEqual(4, after['reviews'][0]['rating'])
        self.assertNotIn(order.id, after['eligible_order_ids'])
        with self.assertRaises(HTTPException):
            order_service.review(self.db, self.outsider, order.id, ReviewInput(restaurant=5, text='Forbidden review'))

    def test_invalid_schedule_rejected(self):
        with self.assertRaises(HTTPException) as error:
            service.set_plan(self.db, self.host, self.store.id, '2000-01-01T00:00:00+00:00')
        self.assertEqual(422, error.exception.status_code)

    def test_closed_restaurant_does_not_leave_schedule_pending_forever(self):
        order = self.scheduled_order()
        schedule = self.db.get(ScheduledOrder, order.id)
        schedule.release_at = datetime.utcnow() - timedelta(minutes=16)
        self.db.flush()
        service.release_due(self.db, [order.id])
        self.assertEqual('REJECTED', order.status)
        self.assertTrue(schedule.released)

    def test_customer_photo_pagination_uses_database_records(self):
        order = self.scheduled_order()
        order.status = 'DELIVERED'; self.db.flush()
        review = order_service.review(self.db, self.host, order.id, ReviewInput(restaurant=5, text='Photo pagination review'))
        for index in range(25):
            self.db.add(File(user_id=self.host.id, purpose='review', entity_id=review.id, path=f'transactional-fixture-{index}', mime='image/jpeg'))
        self.db.flush()
        first = service.customer_photos(self.db, self.store.id, 1)
        second = service.customer_photos(self.db, self.store.id, 2)
        self.assertEqual(24, len(first['items']))
        self.assertTrue(first['has_more'])
        self.assertEqual(1, len(second['items']))
        self.assertFalse(second['has_more'])
        self.assertEqual(25, service.experience(self.db, self.store.id, self.host)['customer_photo_count'])

if __name__ == '__main__':
    unittest.main()
