import hashlib
import hmac


def verify_webhook_signature(
    payload_bytes: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """Verify GitHub webhook signature using HMAC-SHA256.

    GitHub passes the header 'X-Hub-Signature-256' in the format 'sha256=<hex_digest>'.
    Uses hmac.compare_digest to prevent timing attacks.
    """
    if not signature_header or not secret:
        return False

    if not signature_header.startswith("sha256="):
        return False

    expected_hash = signature_header[7:].strip()
    if not expected_hash:
        return False

    computed_mac = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_mac, expected_hash)
