"""Вход и сессия: проверка учётных данных, лимит попыток, выход, смена пароля, вход «как
сотрудник».

Сессия — случайный токен в cookie и запись в таблице user_sessions (core/sessions.py): операции
возвращают токен, cookie ставит роутер. Выход и смена пароля удаляют все сессии пользователя
на всех устройствах.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core import manifest
from app.core.audit import audit
from app.core.auth import Principal
from app.core.auth_guards import assignable_roles, can_manage_user, roles_catalog
from app.core.config import settings
from app.core.db import transactional
from app.core.errors import Forbidden, NotFound, Rejected, TooManyRequests, Unauthorized
from app.core.identity import LoginAttempt, User
from app.core.permissions import principal_permissions
from app.core.security import (
    MIN_PASSWORD_LEN,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.core.sessions import open_session, revoke_session, revoke_user_sessions
from app.core.time import local_date, local_iso, now, to_local
from app.modules.people.application import Employee
from app.modules.timesheet.application.punch_plan import plan_for_date

# лимит входа: неудачи за окно — на пару «адрес + логин» и на адрес целиком (перебор логинов).
# Счётчик — таблица login_attempts: он общий для всех процессов сервера.
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_ATTEMPTS = 10
LOGIN_MAX_PER_IP = 50

_DUMMY_HASH = hash_password("dummy-password-for-timing")


# ─────────────────────────── лимит попыток ───────────────────────────

def _window_start() -> dt.datetime:
    return now() - dt.timedelta(seconds=LOGIN_WINDOW_SECONDS)


def attempt_key(ip: str, username: str) -> str:
    """Ключ счётчика — пара «адрес + логин»: чужие неудачи с того же адреса вход не блокируют,
    а свой успешный вход не сбрасывает счётчик перебора чужого пароля."""
    return f"ip:{ip}|user:{username.strip().lower()[:26]}"


def _too_many_attempts(db: Session, ip: str, username: str) -> bool:
    recent = select(func.count()).select_from(LoginAttempt).where(LoginAttempt.ts >= _window_start())
    if (db.scalar(recent.where(LoginAttempt.key == attempt_key(ip, username))) or 0) >= LOGIN_MAX_ATTEMPTS:
        return True
    return (db.scalar(recent.where(LoginAttempt.key.like(f"ip:{ip}|%"))) or 0) >= LOGIN_MAX_PER_IP


def _record_failure(db: Session, ip: str, username: str) -> None:
    """Записать неудачную попытку — своей фиксацией: вход отказом откатил бы и её.
    Заодно удаляются записи старше окна, таблица не растёт."""
    db.execute(delete(LoginAttempt).where(LoginAttempt.ts < _window_start()))
    db.add(LoginAttempt(key=attempt_key(ip, username)))
    db.commit()


# ─────────────────────────── вход и выход ───────────────────────────

def _authenticate(db: Session, ip: str, username: str, password: str) -> Principal:
    if _too_many_attempts(db, ip, username):
        raise TooManyRequests("Слишком много неудачных попыток входа. Подождите несколько минут.")
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    # хеш считается и для несуществующего логина: по времени ответа логин не угадать
    stored = user.password_hash if user else _DUMMY_HASH
    if not verify_password(password, stored) or not user:
        _record_failure(db, ip, username)
        raise Unauthorized("Неверный логин или пароль")
    if not user.is_active:
        raise Forbidden("Учётная запись отключена")
    db.execute(delete(LoginAttempt).where(LoginAttempt.key == attempt_key(ip, username)))
    if needs_rehash(stored):
        user.password_hash = hash_password(password)     # хеш со старыми параметрами обновляется при входе
    return Principal(user, db.get(Employee, user.employee_id) if user.employee_id else None)


@transactional
def login(db: Session, ip: str, username: str, password: str, *, via_form: bool = False) -> tuple[Principal, str]:
    """Вход по логину и паролю. Возвращает пользователя и токен сессии."""
    principal = _authenticate(db, ip, username, password)
    audit(db, principal, "login", f"user:{principal.user.username}" + (" (form)" if via_form else ""))
    return principal, open_session(db, principal.user, principal.employee.id if principal.employee else None)


@transactional
def logout(db: Session, principal: Principal) -> None:
    """Выход: все сессии пользователя удаляются — украденная cookie перестаёт работать."""
    user = principal.user
    revoke_user_sessions(db, user.id)
    audit(db, principal, "logout", f"user:{user.username}")


@transactional
def change_password(db: Session, principal: Principal, old_password: str, new_password: str) -> str:
    """Сменить свой пароль. Прежние сессии отзываются; возвращается новый токен этой сессии."""
    user = principal.user
    if not verify_password(old_password, user.password_hash):
        raise Rejected("Неверный текущий пароль")
    if len(new_password) < MIN_PASSWORD_LEN:
        raise Rejected(f"Новый пароль слишком короткий (минимум {MIN_PASSWORD_LEN} символов)")
    user.password_hash = hash_password(new_password)
    revoke_user_sessions(db, user.id)
    audit(db, principal, "password_change", f"user:{user.username}")
    return open_session(db, user, principal.employee.id if principal.employee else None, principal.impersonated)


# ─────────────────────────── вход «как сотрудник» ───────────────────────────

@transactional
def impersonate(db: Session, principal: Principal, employee_id: int) -> tuple[Principal, str]:
    """Смотреть интерфейс глазами сотрудника, без его пароля. Войти можно только «как» того,
    чьей учётной записью действующий управляет по иерархии ролей."""
    if not settings.allow_impersonation:
        raise Forbidden("Вход от имени сотрудника отключён")
    employee = db.get(Employee, employee_id)
    if not employee or not employee.active:
        raise NotFound("Сотрудник не найден")
    can_manage_user(db, principal, db.scalar(select(User).where(User.employee_id == employee.id)))
    audit(db, principal, "impersonate", f"employee:{employee.id}", {"employee": employee.full_name})
    if principal.session_id is not None:
        revoke_session(db, principal.session_id)
    return Principal(principal.user, employee, True), open_session(db, principal.user, employee.id, True)


@transactional
def stop_impersonation(db: Session, principal: Principal) -> tuple[Principal, str]:
    if not principal.impersonated:
        raise Rejected("Вы не в режиме просмотра от имени сотрудника")
    employee = db.get(Employee, principal.user.employee_id) if principal.user.employee_id else None
    audit(db, principal, "impersonate_stop", "")
    if principal.session_id is not None:
        revoke_session(db, principal.session_id)
    return Principal(principal.user, employee), open_session(db, principal.user, employee.id if employee else None)


# ─────────────────────────── текущий пользователь ───────────────────────────

def me(db: Session, principal: Principal) -> dict:
    """Текущий пользователь: права, роли, меню и экраны по правам, план на сегодня."""
    perms = set(principal_permissions(db, principal))
    data = {"user": principal.to_dict(), "auth_context": principal.auth_context,
            "today": None, "permissions": sorted(perms),
            "roles": [{"code": r.code, "title": r.title} for r in roles_catalog(db)],
            "assignable_roles": assignable_roles(db, principal),
            **manifest.ui_for(perms)}
    if principal.employee:
        today = local_date()
        shift, planned_start, planned_end, _plan_date, parts = plan_for_date(db, principal.employee.id, today)
        data["today"] = {
            "date": today.isoformat(),
            "shift": shift,              # отрезок Графика либо None
            "planned_start": local_iso(planned_start, "minutes"),
            "planned_end": local_iso(planned_end, "minutes"),
            "expected": [[to_local(a).strftime("%H:%M"), to_local(b).strftime("%H:%M")] for a, b in parts],
        }
    return data
