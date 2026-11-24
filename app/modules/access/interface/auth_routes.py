"""Вход, выход, текущий пользователь, смена пароля, вход «как сотрудник».
Правила — в ``application/auth.py``; здесь — cookie сессии."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.auth import Principal, current_principal
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import ServiceError
from app.core.net import client_ip
from app.core.permissions import require_perm
from app.core.schemas import Ok
from app.core.sessions import session_context

from ..application import auth
from .schemas import AuthContextOut, ChangePasswordIn, ImpersonateIn, LoginIn, MeOut, PasswordChangedOut, SessionOut

router = APIRouter(prefix="/api/auth", tags=["auth"])

# код ошибки входа для формы: в адрес уходит он, а не текст и не пароль
FORM_ERROR_CODES = {429: "rate", 401: "auth", 403: "disabled"}


def _set_context_cookie(response: Response, context: str) -> None:
    # A readable notification for the UI. Authentication only consumes the HttpOnly session cookie.
    response.set_cookie("tt_auth_context", context, max_age=settings.session_ttl_hours * 3600,
                        httponly=False, samesite="lax", path="/", secure=settings.cookie_secure)


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(settings.cookie_name, token, max_age=settings.session_ttl_hours * 3600,
                        httponly=True, samesite="lax", path="/", secure=settings.cookie_secure)
    _set_context_cookie(response, session_context(token))


@router.post("/login", response_model=SessionOut)
def login(payload: LoginIn, response: Response, request: Request, db: Session = Depends(get_db)):
    principal, token = auth.login(db, client_ip(request), payload.username, payload.password)
    _set_cookie(response, token)
    return {"user": principal.to_dict(), "auth_context": session_context(token)}


@router.get("/login-form", response_class=RedirectResponse)
def login_form_get():
    """Адрес формы входа принимает только POST. GET приходит от восстановленных вкладок —
    возвращаем в приложение, а не показываем «Not found»."""
    return RedirectResponse("/", status_code=303)


@router.post("/login-form", response_class=RedirectResponse)
def login_form(request: Request, username: str = Form(""), password: str = Form(""), db: Session = Depends(get_db)):
    """Вход обычной формой с переадресацией: так менеджеры паролей браузера сразу предлагают
    сохранить пароль. Ошибка уходит кодом в адрес."""
    try:
        _principal, token = auth.login(db, client_ip(request), username, password, via_form=True)
    except ServiceError as exc:
        return RedirectResponse(f"/?login_error={FORM_ERROR_CODES.get(exc.status_code, 'auth')}", status_code=303)
    response = RedirectResponse("/", status_code=303)
    _set_cookie(response, token)
    return response


@router.post("/logout", response_model=Ok)
def logout(response: Response, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Выход: cookie удаляется, а все сессии пользователя отзываются на сервере."""
    auth.logout(db, principal)
    response.delete_cookie(settings.cookie_name, path="/")
    _set_context_cookie(response, "signed-out")
    return Ok()


@router.get("/me", response_model=MeOut)
def me(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Текущий пользователь, его права, меню и план на сегодня."""
    return auth.me(db, principal)


@router.get("/context", response_model=AuthContextOut)
def context(principal: Principal = Depends(current_principal)):
    """Отпечаток сессии текущего запроса."""
    return {"auth_context": principal.auth_context}


@router.post("/change-password", response_model=PasswordChangedOut)
def change_password(payload: ChangePasswordIn, response: Response,
                    principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Сменить свой пароль; остальные сессии пользователя перестают действовать."""
    token = auth.change_password(db, principal, payload.old_password, payload.new_password)
    _set_cookie(response, token)
    return PasswordChangedOut(auth_context=session_context(token))


@router.post("/impersonate", response_model=SessionOut)
def impersonate(payload: ImpersonateIn, response: Response,
                principal: Principal = Depends(require_perm("employees.impersonate")),
                db: Session = Depends(get_db)):
    """Смотреть интерфейс глазами сотрудника."""
    shown, token = auth.impersonate(db, principal, payload.employee_id)
    _set_cookie(response, token)
    return {"user": shown.to_dict(), "auth_context": session_context(token)}


@router.post("/impersonate/stop", response_model=SessionOut)
def stop_impersonate(response: Response, principal: Principal = Depends(current_principal),
                     db: Session = Depends(get_db)):
    shown, token = auth.stop_impersonation(db, principal)
    _set_cookie(response, token)
    return {"user": shown.to_dict(), "auth_context": session_context(token)}
