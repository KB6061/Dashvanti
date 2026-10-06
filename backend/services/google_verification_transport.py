import threading
import requests
from cachecontrol import CacheControl
from google.auth.transport.requests import Request

_local = threading.local()


class GoogleVerificationRequest(Request):
    def __call__(self, url, method='GET', body=None, headers=None, timeout=None, **kwargs):
        return super().__call__(url, method, body, headers, timeout=5, **kwargs)


def cached_request():
    if not hasattr(_local, 'request'):
        _local.request = GoogleVerificationRequest(session=CacheControl(requests.Session()))
    return _local.request
