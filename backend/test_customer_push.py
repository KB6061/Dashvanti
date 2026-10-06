import time
import unittest
import uuid
from types import SimpleNamespace
from fastapi import HTTPException
from backend.db import Session
from backend.models import User
from backend.customer_push_models import CustomerPushDevice
from backend.routers.customer_push_router import DeviceRegistration
from backend.services.customer_push_device_service import register, remove
from backend.services.customer_push_service import delivery_data


class CustomerPushTest(unittest.TestCase):
    def setUp(self):
        self.db = Session()
        self.addCleanup(self.db.close)
        self.addCleanup(self.db.rollback)
        self.users = []
        for _ in range(2):
            user = User(email=f'push-audit-{uuid.uuid4()}@example.com', name='Push transactional audit', password='disabled-test-account', role='customer')
            self.db.add(user); self.db.flush(); self.users.append(user)
        self.data = DeviceRegistration(installation_id=str(uuid.uuid4()), token='test-token-' + uuid.uuid4().hex)

    def test_device_registration_and_owner_only_delete(self):
        register(self.db, self.users[0], self.data); self.db.flush()
        remove(self.db, self.users[1], self.data.installation_id)
        self.assertIsNotNone(self.db.get(CustomerPushDevice, self.data.installation_id))
        self.db.expire_all()
        remove(self.db, self.users[0], self.data.installation_id)
        self.assertIsNone(self.db.get(CustomerPushDevice, self.data.installation_id))

    def test_cannot_hijack_another_installation_with_different_token(self):
        register(self.db, self.users[0], self.data); self.db.flush()
        other = DeviceRegistration(installation_id=self.data.installation_id, token='other-token-' + uuid.uuid4().hex)
        with self.assertRaises(HTTPException) as error:
            register(self.db, self.users[1], other)
        self.assertEqual(409, error.exception.status_code)

    def test_no_fake_eta_and_only_customer_leg_estimates(self):
        event = SimpleNamespace(id=1, order_id=2, payload={'activity_status': 'PICKED_UP'})
        self.assertNotIn('eta_seconds', delivery_data(event))
        navigation = {'stage': 'restaurant', 'eta_seconds': 120, 'timestamp': time.time() * 1000}
        self.assertNotIn('eta_seconds', delivery_data(event, navigation))
        navigation['stage'] = 'customer'
        self.assertEqual('120', delivery_data(event, navigation)['eta_seconds'])
        navigation['timestamp'] -= 40000
        self.assertNotIn('eta_seconds', delivery_data(event, navigation))

    def test_non_customer_cannot_register(self):
        self.users[0].role = 'driver'
        with self.assertRaises(HTTPException) as error:
            register(self.db, self.users[0], self.data)
        self.assertEqual(403, error.exception.status_code)


if __name__ == '__main__':
    unittest.main()
