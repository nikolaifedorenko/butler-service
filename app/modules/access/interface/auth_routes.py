"""Аутентификация, профиль, «войти как сотрудник» для демонстрации."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal, current_principal
from app.core.auth_guards import can_manage_user
from app.core.config import settings
from app.core.db import get_db
from app.core.identity import LoginAttempt, User
from app.core.permissions import require_perm
from app.core.security import MIN_PASSWORD_LEN, create_token, hash_password, needs_rehash, verify_password
from app.core.time import local_date, utcnow
from app.modules.employees.application import Employee

router = APIRouter(prefix="/api/auth", tags=["auth"])


_DUMMY_HASH = hash_password("dummy-password-for-timing")

# ── rate-limit входа: не более MAX неудач с одного IP за WINDOW секунд ──────────
# Счётчик — таблица login_attempts (ADR-0005, пересмотрен 22.10.2026): раньше словарь в
# памяти каждого воркера, и при N воркерах лимит фактически был ×N (SEC-01).
_LOGIN_WINDOW_SECONDS = 300
_LOGIN_MAX_ATTEMPTS = 10        # на пару «адрес + логин»
_LOGIN_MAX_PER_IP = 50          # на адрес целиком: перебор по разным логинам


def _client_ip(request: Request) -> str:
    # Без reverse-proxy адрес клиента — адрес соединения. За прокси это адрес прокси
    # (все клиенты в одном бакете лимита), поэтому X-Forwarded-For читается ТОЛЬКО
    # при TRUST_PROXY_HEADERS=1 — включайте, когда приложение гарантированно стоит
    # за своим доверенным прокси (nginx из docker-compose.prod.yml), иначе заголовок
    # подделывается клиентом и лимит обходится/направляется на чужой IP.
    if settings.trust_proxy_headers:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            # правый адрес дописал наш nginx ($proxy_add_x_forwarded_for); левые присылает
            # клиент — по ним лимит обходился сменой заголовка (аудит 21.10.2026, SEC-01)
            return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _window_start() -> dt.datetime:
    return utcnow() - dt.timedelta(seconds=_LOGIN_WINDOW_SECONDS)


def _attempt_key(ip: str, username: str) -> str:
    """Счётчик — на пару «адрес + логин» (аудит 22.10.2026): раньше общий на адрес, и свой
    успешный вход сбрасывал его — перебор чужого пароля шёл без остановки, а персонал за
    одним Wi-Fi блокировал вход друг другу. Колонка — 80 символов, логин в ключе обрезаем."""
    return f"ip:{ip}|user:{username.strip().lower()[:26]}"


def _too_many_attempts(db: Session, ip: str, username: str) -> bool:
    recent = select(func.count()).select_from(LoginAttempt).where(LoginAttempt.ts >= _window_start())
    if db.scalar(recent.where(LoginAttempt.key == _attempt_key(ip, username))) >= _LOGIN_MAX_ATTEMPTS:
        return True
    return db.scalar(recent.where(LoginAttempt.key.like(f"ip:{ip}|%"))) >= _LOGIN_MAX_PER_IP


def _record_login_failure(db: Session, ip: str, username: str) -> None:
    """Отдельный commit сразу: за ним 401, и без него попытка пропала бы вместе с сессией.
    Заодно убираем записи старше окна — таблица не растёт, фоновая задача не нужна."""
    db.execute(delete(LoginAttempt).where(LoginAttempt.ts < _window_start()))
    db.add(LoginAttempt(key=_attempt_key(ip, username)))
    db.commit()


def _reset_login_failures(db: Session, ip: str, username: str) -> None:
    """Успешный вход сбрасывает только свою пару: чужие неудачи с этого адреса остаются."""
    db.execute(delete(LoginAttempt).where(LoginAttempt.key == _attempt_key(ip, username)))


def _token(user: User, emp_id, imp: bool = False) -> str:
    body = {"uid": user.id, "emp_id": emp_id, "tv": int(user.token_version or 0)}
    if imp:
        body["imp"] = True
    return create_token(body)


class LoginIn(BaseModel):
    username: str
    password: str


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.cookie_name, token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True, samesite="lax", path="/",
        secure=settings.cookie_secure,
    )


def _authenticate(db: Session, request: Request, username: str, password: str):
    """Общая проверка учётных данных для JSON- и форм-входа (rate-limit, постоянный
    хеш для несуществующего логина, ленивый rehash). Возвращает (user, employee)."""
    ip = _client_ip(request)
    if _too_many_attempts(db, ip, username):
        raise HTTPException(status_code=429,
                            detail="Слишком много неудачных попыток входа. Подождите несколько минут.")
    user = db.scalar(select(User).where(User.username == username.strip().lower()))
    # для несуществующего логина тоже считаем хеш — по времени ответа логин не угадать
    stored = user.password_hash if user else _DUMMY_HASH
    if not verify_password(password, stored) or not user:
        _record_login_failure(db, ip, username)
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Учётная запись отключена")
    _reset_login_failures(db, ip, username)
    if needs_rehash(stored):
        # ленивая миграция хеша: старые записи (например, 120k итераций) обновляются
        # на текущие параметры при успешном входе — пароль у нас в этот момент есть
        user.password_hash = hash_password(password)
    employee = db.get(Employee, user.employee_id) if user.employee_id else None
    return user, employee


@router.post("/login")
def login(payload: LoginIn, response: Response, request: Request, db: Session = Depends(get_db)):
    user, employee = _authenticate(db, request, payload.username, payload.password)
    token = _token(user, employee.id if employee else None)
    _set_cookie(response, token)
    audit(db, Principal(user, employee), "login", f"user:{user.username}")
    db.commit()
    return {"ok": True, "user": Principal(user, employee).to_dict()}


@router.get("/login-form")
def login_form_get():
    """Адрес действия формы логина принимает только POST (303-редирект).

    GET сюда приходит лишь от восстановленных вкладок и пробных запросов браузера
    (18.10.2026: владелец видел на таком URL JSON «Not found» после перезапуска
    сервера). Возвращаем в приложение, а не JSON 404.
    """
    return RedirectResponse("/", status_code=303)


@router.post("/login-form")
def login_form(request: Request, username: str = Form(""), password: str = Form(""),
               db: Session = Depends(get_db)):
    """Классический form-login с редиректом — ДЛЯ МЕНЕДЖЕРОВ ПАРОЛЕЙ (16.10.2026).

    Браузерные менеджеры (Safari/«Пароли» macOS включительно) надёжно распознают
    связку «submit формы с паролем → 303-редирект» и показывают «Сохранить пароль?»
    сразу после входа. SPA-вход через preventDefault+fetch они откладывают до
    следующего действия пользователя — владелец видел плашку при открытии
    «Настроек». Ошибки уносим кодом в URL: пароль в адресную строку не попадает."""
    from fastapi import HTTPException as _HE
    try:
        user, employee = _authenticate(db, request, username, password)
    except _HE as exc:
        code = {429: "rate", 401: "auth", 403: "disabled"}.get(exc.status_code, "auth")
        return RedirectResponse(f"/?login_error={code}", status_code=303)
    resp = RedirectResponse("/", status_code=303)
    token = _token(user, employee.id if employee else None)
    _set_cookie(resp, token)
    audit(db, Principal(user, employee), "login", f"user:{user.username} (form)")
    db.commit()
    return resp


@router.post("/logout")
def logout(response: Response, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Выход: cookie удаляется у клиента И отзывается на сервере.

    Токен stateless, поэтому одного delete_cookie мало — скопированная/украденная
    cookie продолжала бы работать до истечения срока. Увеличение token_version
    делает недействительными все ранее выданные токены пользователя (на всех
    устройствах) — так же, как при смене пароля.
    """
    user = principal.user
    user.token_version = int(user.token_version or 0) + 1
    audit(db, principal, "logout", f"user:{user.username}")
    db.commit()
    response.delete_cookie(settings.cookie_name, path="/")
    return {"ok": True}


@router.get("/me")
def me(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Текущий пользователь + его план на сегодня (для личного кабинета)."""
    emp = principal.employee
    from app.core import manifest
    from app.core.auth_guards import assignable_roles, roles_catalog
    from app.core.permissions import principal_permissions

    perms = set(principal_permissions(db, principal))
    data = {"user": principal.to_dict(), "today": None,
            "permissions": sorted(perms),
            # роли как данные (ADR-0011): названия для экранов и роли, которые можно назначать
            "roles": [{"code": r.code, "title": r.title} for r in roles_catalog(db)],
            "assignable_roles": assignable_roles(db, principal),
            # меню и экраны Настроек из манифестов модулей, уже по правам (шаг 5.4)
            **manifest.ui_for(perms)}
    if emp:
        from app.modules.timesheet.application.punch_plan import plan_for_date, to_local
        today = local_date()
        shift, p_start, p_end, _plan_date, subs = plan_for_date(db, emp.id, today)
        data["today"] = {
            "date": today.isoformat(),
            "shift": shift,      # отрезок Графика (generated/manual) либо None
            "planned_start": p_start.isoformat(timespec="minutes") if p_start else None,
            "planned_end": p_end.isoformat(timespec="minutes") if p_end else None,
            "expected": [[to_local(a).strftime("%H:%M"), to_local(b).strftime("%H:%M")]
                         for a, b in subs],
        }
    return data


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str


@router.post("/change-password")
def change_password(payload: ChangePasswordIn, response: Response, principal: Principal = Depends(current_principal),
                    db: Session = Depends(get_db)):
    """Смена своего пароля: старый пароль для проверки + новый (подтверждение проверяет клиент)."""
    if not verify_password(payload.old_password, principal.user.password_hash):
        raise HTTPException(status_code=400, detail="Неверный текущий пароль")
    if len(payload.new_password) < MIN_PASSWORD_LEN:
        raise HTTPException(status_code=400,
                            detail=f"Новый пароль слишком короткий (минимум {MIN_PASSWORD_LEN} символов)")
    user = principal.user
    user.password_hash = hash_password(payload.new_password)
    # все прежние сессии (другие устройства, украденные cookie) становятся недействительными
    user.token_version = int(user.token_version or 0) + 1
    audit(db, principal, "password_change", f"user:{user.username}")
    db.commit()
    emp_id = principal.employee.id if principal.employee else None
    _set_cookie(response, _token(user, emp_id, principal.impersonated))
    return {"ok": True}


class ImpersonateIn(BaseModel):
    employee_id: int


@router.post("/impersonate")
def impersonate(payload: ImpersonateIn, response: Response,
                principal: Principal = Depends(require_perm("employees.impersonate")), db: Session = Depends(get_db)):
    """Демо-режим: менеджер смотрит интерфейс глазами сотрудника (без пароля)."""
    if not settings.allow_impersonation:
        raise HTTPException(status_code=403, detail="Вход от имени сотрудника отключён")
    emp = db.get(Employee, payload.employee_id)
    if not emp or not emp.active:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    # иерархия ролей: supervisor не входит «как» manager/admin (аудит 21.10.2026, AUTHZ-01)
    can_manage_user(db, principal, db.scalar(select(User).where(User.employee_id == emp.id)))
    token = _token(principal.user, emp.id, imp=True)
    _set_cookie(response, token)
    audit(db, principal, "impersonate", f"employee:{emp.id}", {"employee": emp.full_name})
    db.commit()
    return {"ok": True, "user": Principal(principal.user, emp, True).to_dict()}


@router.post("/impersonate/stop")
def stop_impersonate(response: Response, principal: Principal = Depends(current_principal),
                     db: Session = Depends(get_db)):
    if not principal.impersonated:
        raise HTTPException(status_code=400, detail="Вы не в режиме просмотра от имени сотрудника")
    emp = db.get(Employee, principal.user.employee_id) if principal.user.employee_id else None
    token = _token(principal.user, emp.id if emp else None)
    _set_cookie(response, token)
    audit(db, principal, "impersonate_stop", "")
    db.commit()
    return {"ok": True, "user": Principal(principal.user, emp).to_dict()}

