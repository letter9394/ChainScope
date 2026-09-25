from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from sqlalchemy import select

from app.database import Database, EmailVerificationRow, UserRow, utcnow
from app.models import AuthUser


def _urlsafe_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${_urlsafe_encode(salt)}${_urlsafe_encode(derived)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_urlsafe_decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return hmac.compare_digest(actual, _urlsafe_decode(expected))
    except (ValueError, TypeError):
        return False


def password_fingerprint(encoded: str) -> str:
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def create_password_reset_token(user: UserRow, secret: str, max_age_seconds: int) -> str:
    payload = json.dumps(
        {
            "sub": user.id,
            "exp": int(time.time()) + max_age_seconds,
            "purpose": "password_reset",
            "pwd": password_fingerprint(user.password_hash),
        },
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = _urlsafe_encode(payload)
    signature = _urlsafe_encode(
        hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{encoded}.{signature}"


def decode_password_reset_token(token: str, secret: str) -> tuple[int, str] | None:
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = _urlsafe_encode(
            hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        payload = json.loads(_urlsafe_decode(encoded))
        if payload.get("purpose") != "password_reset" or int(payload["exp"]) < int(time.time()):
            return None
        return int(payload["sub"]), str(payload["pwd"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def create_email_verification_token(user: UserRow, secret: str, max_age_seconds: int) -> str:
    email_fingerprint = hashlib.sha256(user.email.encode("utf-8")).hexdigest()[:24]
    payload = json.dumps(
        {
            "sub": user.id,
            "exp": int(time.time()) + max_age_seconds,
            "purpose": "email_verification",
            "email": email_fingerprint,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = _urlsafe_encode(payload)
    signature = _urlsafe_encode(
        hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{encoded}.{signature}"


def decode_email_verification_token(token: str, secret: str) -> tuple[int, str] | None:
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = _urlsafe_encode(
            hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        payload = json.loads(_urlsafe_decode(encoded))
        if payload.get("purpose") != "email_verification" or int(payload["exp"]) < int(time.time()):
            return None
        return int(payload["sub"]), str(payload["email"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def create_session_token(user_id: int, secret: str, max_age_seconds: int) -> str:
    payload = json.dumps(
        {"sub": user_id, "exp": int(time.time()) + max_age_seconds},
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = _urlsafe_encode(payload)
    signature = _urlsafe_encode(hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def decode_session_token(token: str, secret: str) -> int | None:
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = _urlsafe_encode(
            hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        payload = json.loads(_urlsafe_decode(encoded))
        if int(payload["exp"]) < int(time.time()):
            return None
        return int(payload["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def user_model(row: UserRow, *, email_verified: bool = True) -> AuthUser:
    return AuthUser(
        id=row.id,
        email=row.email,
        created_at=row.created_at.isoformat(),
        email_verified=email_verified,
    )


class UserRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get_by_email(self, email: str) -> UserRow | None:
        with self.database.session() as session:
            return session.scalar(select(UserRow).where(UserRow.email == email.strip().lower()))

    def get_by_id(self, user_id: int) -> UserRow | None:
        with self.database.session() as session:
            return session.get(UserRow, user_id)

    def create(self, email: str, password: str) -> UserRow:
        row = UserRow(email=email.strip().lower(), password_hash=hash_password(password))
        with self.database.session() as session:
            session.add(row)
            session.flush()
            session.add(EmailVerificationRow(user_id=row.id))
            session.commit()
            session.refresh(row)
        return row

    def is_email_verified(self, user_id: int) -> bool:
        with self.database.session() as session:
            verification = session.get(EmailVerificationRow, user_id)
            # Accounts created before verification support have no row and stay verified.
            return verification is None or verification.verified_at is not None

    def verify_email(self, user_id: int, expected_email_fingerprint: str) -> UserRow | None:
        with self.database.session() as session:
            row = session.get(UserRow, user_id)
            if row is None:
                return None
            actual_fingerprint = hashlib.sha256(row.email.encode("utf-8")).hexdigest()[:24]
            if not hmac.compare_digest(actual_fingerprint, expected_email_fingerprint):
                return None
            verification = session.get(EmailVerificationRow, user_id)
            if verification is not None and verification.verified_at is None:
                verification.verified_at = utcnow()
                session.commit()
            session.refresh(row)
            return row

    def reset_password(self, user_id: int, expected_fingerprint: str, password: str) -> UserRow | None:
        with self.database.session() as session:
            row = session.get(UserRow, user_id)
            if row is None or not hmac.compare_digest(
                password_fingerprint(row.password_hash), expected_fingerprint
            ):
                return None
            row.password_hash = hash_password(password)
            session.commit()
            session.refresh(row)
            return row
