"""Сессии в базе и argon2id (ADR-0013, раздел 8): токен случайный, в таблице — только его SHA-256;
отзыв — удалением записи; выход завершает сессии на всех устройствах."""
from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import settings
from app.core.identity import User, UserSession
from app.core.security import token_digest
from app.core.sessions import open_session


def _login(app_stack, username="ivanov") -> TestClient:
    c = TestClient(app_stack["app"])
    assert c.post("/api/auth/login", json={"username": username, "password": "demo1234"}).status_code == 200
    return c


def test_login_stores_only_token_digest(app_stack, db):
    c = _login(app_stack)
    token = c.cookies.get(settings.cookie_name)
    assert len(token) >= 40 and "." not in token, "токен — случайная строка, а не подписанная структура"
    rows = db.scalars(select(UserSession)).all()
    assert token not in {r.token_hash for r in rows}
    assert token_digest(token) in {r.token_hash for r in rows}


def test_logout_revokes_all_devices(app_stack, db):
    phone, laptop = _login(app_stack), _login(app_stack)
    assert phone.get("/api/auth/me").status_code == 200 and laptop.get("/api/auth/me").status_code == 200
    assert laptop.post("/api/auth/logout").status_code == 200
    assert phone.get("/api/auth/me").status_code == 401
    user = db.scalar(select(User).where(User.username == "ivanov"))
    assert db.scalar(select(func.count()).select_from(UserSession).where(UserSession.user_id == user.id)) == 0


def test_impersonation_replaces_session(app_stack, db):
    admin = _login(app_stack, "admin")
    before = admin.cookies.get(settings.cookie_name)
    emp = admin.get("/api/employees").json()
    target = next(e for e in emp if e.get("username") == "ivanov" or e.get("full_name", "").startswith("Иванов"))
    r = admin.post("/api/auth/impersonate", json={"employee_id": target["id"]})
    assert r.status_code == 200, r.text
    after = admin.cookies.get(settings.cookie_name)
    assert after != before
    old = TestClient(app_stack["app"])
    old.cookies.set(settings.cookie_name, before)
    assert old.get("/api/auth/me").status_code == 401, "прежняя сессия не должна жить рядом с «как сотрудник»"
    me = admin.get("/api/auth/me").json()
    assert me["user"]["impersonated"] is True
    assert admin.post("/api/auth/impersonate/stop").status_code == 200
    assert admin.get("/api/auth/me").json()["user"]["impersonated"] is False


def test_expired_sessions_are_purged_on_open(app_stack, db):
    user = db.scalar(select(User).where(User.username == "ivanov"))
    stale = open_session(db, user, user.employee_id)
    db.flush()
    row = db.scalar(select(UserSession).where(UserSession.token_hash == token_digest(stale)))
    row.expires_at = dt.datetime(2000, 1, 1, tzinfo=dt.UTC)
    db.commit()
    open_session(db, user, user.employee_id)
    db.commit()
    assert db.scalar(select(UserSession).where(UserSession.token_hash == token_digest(stale))) is None


def test_deactivated_user_session_is_refused(app_stack, db):
    c = _login(app_stack, "smirnov")
    user = db.scalar(select(User).where(User.username == "smirnov"))
    user.is_active = False
    db.commit()
    try:
        assert c.get("/api/auth/me").status_code == 401
    finally:
        user.is_active = True
        db.commit()
