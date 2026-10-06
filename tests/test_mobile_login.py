import unittest
from unittest.mock import patch
from backend.models import User
from backend.services.auth_service import passwords
import test_admin_portal as fixtures

class MobileLoginTest(unittest.TestCase):
    setUp = fixtures.AdminPortalTest.setUp
    tearDown = fixtures.AdminPortalTest.tearDown

    def prepare(self):
        user=self.db.get(User,self.people['customer'])
        user.phone='+1 (615) 555-0198'
        user.password=passwords.hash('MobileAuditPassword1')
        self.db.commit()
        return user

    def login(self,number,password='MobileAuditPassword1'):
        with patch('backend.services.auth_service.emit'):
            return self.client.post('/api/auth/login',json={'email':number,'password':password,'role':'customer'})

    def test_mobile_and_email_issue_existing_jwt_session(self):
        user=self.prepare()
        for identifier in ['+1 (615) 555-0198','16155550198',user.email]:
            response=self.login(identifier)
            self.assertEqual(response.status_code,200,response.text)
            data=response.json()
            self.assertIn('refresh_token',data)
            me=self.client.get('/api/me',headers={'Authorization':'Bearer '+data['access_token']})
            self.assertEqual(me.json()['id'],user.id)

    def test_wrong_password_unknown_and_ambiguous_numbers_are_denied(self):
        self.prepare()
        self.assertEqual(self.login('16155550198','incorrect').status_code,401)
        self.assertEqual(self.login('19995550199').status_code,401)
        duplicate=User(email='mobile-audit-duplicate@example.com',name='Mobile duplicate',role='customer',phone='16155550198',password=passwords.hash('MobileAuditPassword1'))
        self.db.add(duplicate);self.db.commit()
        self.assertEqual(self.login('16155550198').status_code,401)

if __name__=='__main__':unittest.main()
