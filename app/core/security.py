"""Пароли (argon2id) и токен сессии (случайная строка; запись о сессии — в таблице user_sessions)."""
from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSWORD_LEN = 8    # одно правило для смены своего пароля, учёток и администратора сида

# параметры по умолчанию argon2-cffi — профиль RFC 9106 (argon2id); при их ужесточении старые хеши
# пересчитываются при следующем входе (needs_rehash)
_HASHER = PasswordHasher()


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(password: str, stored: str) -> bool:
    try:
        return _HASHER.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(stored: str) -> bool:
    """Хеш создан с прежними параметрами — при следующем успешном входе его пересчитывают
    (ленивая миграция без сброса паролей). Не argon2id-строка (чужой формат) — тоже пересчёт."""
    try:
        return _HASHER.check_needs_rehash(stored)
    except InvalidHashError:
        return True


def new_csrf_token() -> str:
    """Случайный CSRF-токен (double-submit cookie)."""
    return secrets.token_hex(16)


def new_session_token() -> str:
    """Токен сессии для cookie: 256 бит случайности. В базе хранится только его SHA-256."""
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    """Отпечаток токена для поиска записи сессии: утечка таблицы не даёт рабочих cookie.
    Токен случайный и длинный, поэтому быстрый хеш без соли достаточен."""
    return hashlib.sha256(token.encode()).hexdigest()
