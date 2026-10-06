import unittest
from backend.models import Driver, DriverLocation, User, now
from backend.services.navigation_service_live import snapshot
import test_admin_portal as fixtures

class NavigationVisibilityTest(unittest.TestCase):
    setUp = fixtures.AdminPortalTest.setUp
    tearDown = fixtures.AdminPortalTest.tearDown

    def test_admin_only_shows_online_drivers_even_without_navigation(self):
        uid = self.people['driver']
        driver = self.db.get(Driver, uid)
        self.db.add(DriverLocation(driver_id=uid, latitude=36, longitude=-86, heading=90, updated_at=now()))
        self.db.commit()
        self.assertNotIn(uid, [row['id'] for row in snapshot(self.db)['drivers']])
        driver.online = True
        self.db.commit()
        response = self.client.get('/api/operations/admin/navigation-state', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn(uid, [row['id'] for row in response.json()['drivers']])
        driver.online = False
        self.db.commit()
        self.assertNotIn(uid, [row['id'] for row in snapshot(self.db)['drivers']])

    def test_customer_snapshot_does_not_expose_other_drivers(self):
        data = snapshot(self.db, self.db.get(User, self.people['customer']))
        self.assertNotIn('drivers', data)
        response = self.client.get('/api/operations/admin/navigation-state')
        self.assertIn(response.status_code, (401, 403))

if __name__ == '__main__':
    unittest.main()
