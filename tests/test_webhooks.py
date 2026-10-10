import hashlib
import hmac
from src.utils.security import verify_webhook_signature


def _compute_sig(payload: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


def test_valid_webhook_signature():
    secret = "super_secret_webhook_key_123"
    payload = b'{"action": "opened", "number": 1}'
    sig = _compute_sig(payload, secret)

    assert verify_webhook_signature(payload, sig, secret) is True


def test_invalid_webhook_signature():
    secret = "super_secret_webhook_key_123"
    payload = b'{"action": "opened", "number": 1}'
    tampered_sig = "sha256=0000000000000000000000000000000000000000000000000000000000000000"

    assert verify_webhook_signature(payload, tampered_sig, secret) is False


def test_tampered_payload():
    secret = "super_secret_webhook_key_123"
    payload = b'{"action": "opened", "number": 1}'
    sig = _compute_sig(payload, secret)
    tampered_payload = b'{"action": "opened", "number": 2}'

    assert verify_webhook_signature(tampered_payload, sig, secret) is False


def test_missing_or_empty_header():
    secret = "my_secret"
    payload = b"data"

    assert verify_webhook_signature(payload, None, secret) is False
    assert verify_webhook_signature(payload, "", secret) is False
    assert verify_webhook_signature(payload, "invalid_prefix_signature", secret) is False


def test_missing_secret():
    payload = b"data"
    assert verify_webhook_signature(payload, "sha256=123", "") is False
