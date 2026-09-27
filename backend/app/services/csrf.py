import hashlib
import hmac
import secrets
import time


def create_csrf_token(secret: str, *, issued_at: int | None = None) -> str:
    timestamp = int(time.time()) if issued_at is None else issued_at
    nonce = secrets.token_urlsafe(32)
    payload = f"{timestamp}.{nonce}"
    signature = hmac.new(
        secret.encode("utf-8"),
        f"chainscope-csrf:{payload}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def validate_csrf_token(
    token: str | None,
    secret: str,
    max_age_seconds: int,
    *,
    now: int | None = None,
) -> bool:
    if not token or len(token) > 512:
        return False
    try:
        timestamp_text, nonce, supplied_signature = token.split(".", 2)
        timestamp = int(timestamp_text)
    except (TypeError, ValueError):
        return False
    if not nonce or len(nonce) > 128 or len(supplied_signature) != 64:
        return False

    current_time = int(time.time()) if now is None else now
    age = current_time - timestamp
    if age < -60 or age > max_age_seconds:
        return False

    payload = f"{timestamp}.{nonce}"
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        f"chainscope-csrf:{payload}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(supplied_signature, expected_signature)
