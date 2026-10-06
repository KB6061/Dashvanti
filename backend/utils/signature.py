import base64
import hashlib
import hmac
import json


def encode_payload(payload):
    return base64.b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode()


def x_verify(encoded_payload, api_path, salt_key, salt_index):
    digest = hashlib.sha256((encoded_payload + api_path + salt_key).encode()).hexdigest()
    return digest + '###' + str(salt_index)


def verify_legacy_callback(encoded_payload, signature, salt_key, salt_index):
    return hmac.compare_digest(x_verify(encoded_payload, '', salt_key, salt_index), signature)


def verify_sha_webhook(authorization, username, password):
    if not username or not password:
        return False
    expected = hashlib.sha256(f'{username}:{password}'.encode()).hexdigest()
    return hmac.compare_digest(expected, authorization)
