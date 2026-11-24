"""Сессии входа в базе (ADR-0013, раздел 8): открыть, найти по токену, отозвать.

Токен — случайная строка в cookie; в таблице user_sessions лежит только его SHA-256. Срок жизни
фиксированный (``session_ttl_hours``). Отзыв — удаление записи: одной сессии (смена режима «как
сотрудник») или всех сессий пользователя (выход, смена пароля, увольнение, удаление). Просроченные
записи удаляются при открытии новой сессии — таблица не растёт.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import settings
from .identity import User, UserSession
from .security import new_session_token, token_digest
from .time import now


def session_context(token: str) -> str:
    """Отпечаток для сравнения сессий. Для доступа используется токен из cookie."""
    return hashlib.sha256(f"butler:auth-context:v1:{token}".encode()).hexdigest()


def open_session(db: Session, user: User, employee_id: Optional[int], impersonated: bool = False) -> str:
    """Новая сессия пользователя; возвращает токен для cookie. Коммитит вызывающий."""
    moment = now()
    db.execute(delete(UserSession).where(UserSession.expires_at < moment))
    token = new_session_token()
    db.add(UserSession(user_id=user.id, token_hash=token_digest(token), employee_id=employee_id,
                       impersonated=impersonated, created_at=moment,
                       expires_at=moment + dt.timedelta(hours=settings.session_ttl_hours)))
    return token


def find_session(db: Session, token: str) -> Optional[UserSession]:
    """Действующая сессия по токену из cookie либо None (нет записи или срок вышел)."""
    row = db.scalar(select(UserSession).where(UserSession.token_hash == token_digest(token)))
    if row is None or row.expires_at < now():
        return None
    return row


def revoke_user_sessions(db: Session, user_id: int) -> None:
    """Завершить все сессии пользователя на всех устройствах. Коммитит вызывающий."""
    db.execute(delete(UserSession).where(UserSession.user_id == user_id))


def revoke_session(db: Session, session_id: int) -> None:
    """Завершить одну сессию. Коммитит вызывающий."""
    db.execute(delete(UserSession).where(UserSession.id == session_id))
