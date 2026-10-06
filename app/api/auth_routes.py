"""Аутентификация, профиль, «войти как сотрудник» для демонстрации."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal, audit, current_principal, require_manager
from ..config import settings
from ..db import get_db
from ..deps import local_date
from ..models import Employee, ScheduleEntry, User
from ..security import create_token, hash_password, verify_password
from ..schedule_helpers import shift_window

router = APIRouter(prefix="/api/auth", tags=["auth"])


_DUMMY_HASH = hash_password("dummy-password-for-timing")
MIN_PASSWORD_LEN = 8


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


@router.post("/login")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username.strip().lower()))
    # для несуществующего логина тоже считаем хеш — по времени ответа логин не угадать
    stored = user.password_hash if user else _DUMMY_HASH
    if not verify_password(payload.password, stored) or not user:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Учётная запись отключена")
    employee = db.get(Employee, user.employee_id) if user.employee_id else None
    token = _token(user, employee.id if employee else None)
    _set_cookie(response, token)
    audit(db, Principal(user, employee), "login", f"user:{user.username}")
    db.commit()
    return {"ok": True, "user": Principal(user, employee).to_dict()}


@router.post("/logout")
def logout(response: Response, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    audit(db, principal, "logout", f"user:{principal.user.username}")
    db.commit()
    response.delete_cookie(settings.cookie_name, path="/")
    return {"ok": True}


@router.get("/me")
def me(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Текущий пользователь + его план на сегодня (для личного кабинета)."""
    emp = principal.employee
    from ..permissions import principal_permissions

    data = {"user": principal.to_dict(), "today": None,
            "permissions": sorted(principal_permissions(db, principal))}
    if emp:
        today = local_date()
        from ..base_schedule import base_shift

        entry = db.scalar(select(ScheduleEntry).where(
            ScheduleEntry.employee_id == emp.id, ScheduleEntry.date == today))
        rules = None
        shift = entry.shift_type if entry else None
        if shift is None:
            shift = base_shift(db, emp, today)
        p_start, p_end = shift_window(shift, today, rules)
        data["today"] = {
            "date": today.isoformat(),
            "shift": None if not shift else {
                "id": shift.id, "code": shift.code, "name": shift.name, "kind": shift.kind,
                "display_code": shift.display_code, "color": shift.color,
                "start": shift.start_time, "end": shift.end_time,
                "overnight": shift.overnight, "planned_hours": shift.planned_hours,
                "is_default_off": shift.is_default_off,
            },
            "note": entry.note if entry else "",
            "planned_start": p_start.isoformat(timespec="minutes") if p_start else None,
            "planned_end": p_end.isoformat(timespec="minutes") if p_end else None,
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
                principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Демо-режим: менеджер смотрит интерфейс глазами сотрудника (без пароля)."""
    if not settings.allow_impersonation:
        raise HTTPException(status_code=403, detail="Вход от имени сотрудника отключён")
    emp = db.get(Employee, payload.employee_id)
    if not emp or not emp.active:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
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


@router.get("/employees-for-demo")
def employees_for_demo(principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Список сотрудников для быстрого переключения в демо-режиме."""
    emps = db.scalars(select(Employee).where(Employee.active.is_(True)).order_by(Employee.full_name)).all()
    return [{"id": e.id, "full_name": e.full_name, "short_name": e.display_name, "position": e.position} for e in emps]
