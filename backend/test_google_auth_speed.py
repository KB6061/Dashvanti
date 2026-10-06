import json
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
import jwt
from fastapi import HTTPException
from backend.db import Session
from backend.config import settings
from backend.services import social_auth_service as social
from backend.services.google_verification_transport import GoogleVerificationRequest, cached_request
from cachecontrol import CacheControl
import requests


class GoogleAuthSpeedTest(unittest.TestCase):
    def test_certificate_http_cache_avoids_repeat_fetch(self):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append(1)
                self.send_response(200)
                self.send_header('Cache-Control', 'public, max-age=300')
                self.send_header('Content-Type', 'application/json')
                self.end_headers(); self.wfile.write(b'{}')
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            session = CacheControl(requests.Session())
            try:
                request = GoogleVerificationRequest(session=session)
                url = f'http://127.0.0.1:{server.server_port}/certs'
                request(url); request(url)
                self.assertEqual(1, len(calls))
            finally:
                session.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_cached_transport_keeps_nonce_and_verified_email_checks(self):
        claims = {'sub': 'provider-test-subject', 'email': 'google-test@example.com', 'email_verified': True, 'iss': 'https://accounts.google.com', 'nonce': 'expected'}
        with patch.object(social.id_token, 'verify_oauth2_token', return_value=claims) as verify:
            social.verify_google('opaque-token', 'expected')
            self.assertIs(verify.call_args.args[1], cached_request())
            self.assertEqual(social.config.google_client_id, verify.call_args.args[2])
            with self.assertRaises(HTTPException): social.verify_google('opaque-token', 'wrong')
            claims['email_verified'] = False
            with self.assertRaises(HTTPException): social.verify_google('opaque-token', 'expected')

    def test_verified_login_returns_user_and_persistent_session_together(self):
        with Session() as db:
            try:
                identity = social.profile('google', str(uuid.uuid4()), 'Google transactional audit', f'google-audit-{uuid.uuid4()}@example.com', None)
                result = social.authenticate(db, identity)
                self.assertEqual('customer', result['user']['role'])
                claims = jwt.decode(result['refresh_token'], settings.jwt_secret, algorithms=['HS256'], audience='dashvanti-session', issuer='dashvanti-api')
                self.assertEqual(str(result['user']['id']), claims['sub'])
                self.assertEqual('persistent-session', claims['kind'])
            finally:
                db.rollback()


if __name__ == '__main__':
    unittest.main()
