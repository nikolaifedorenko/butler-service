"""Пароли (PBKDF2 из stdlib) и подписанные cookie-сессии — без внешних зависимостей."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

from .config import settings

_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS).hex()
    return f"pbkdf2${_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, digest = stored.split("$")
        if algo != "pbkdf2":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters)).hex()
        return hmac.compare_digest(calc, digest)
    except Exception:
        return False


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_token(payload: dict, ttl_hours: Optional[int] = None) -> str:
    ttl = ttl_hours if ttl_hours is not None else settings.session_ttl_hours
    body = dict(payload)
    body["exp"] = int(time.time()) + ttl * 3600
    raw = _b64e(json.dumps(body, separators=(",", ":")).encode())
    sig = hmac.new(settings.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{raw}.{sig}"


def read_token(token: str) -> Optional[dict]:
    try:
        raw, sig = token.split(".")
    except ValueError:
        return None
    expected = hmac.new(settings.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        payload = json.loads(_b64d(raw))
    except Exception:
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload
