"""Сессии в базе и argon2id (ADR-0013, раздел 8): токен случайный, в таблице — только его SHA-256;
отзыв — удалением записи; выход завершает сессии на всех устройствах."""
from __future__ import annotations

import datetime as dt
import re

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core import sessions
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


def test_session_context_distinguishes_tokens_and_digests():
    token = "test-session"
    context = sessions.session_context(token)
    assert re.fullmatch(r"[0-9a-f]{64}", context)
    assert context not in {token, token_digest(token)}
    assert sessions.session_context(token) == context
    assert sessions.session_context("other-session") != context


def test_login_context_matches_current_cookie(client, db):
    login = client.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"})
    assert login.status_code == 200, login.text
    assert login.json()["ok"] is True
    context = client.get("/api/auth/context")
    assert context.status_code == 200, context.text
    fingerprint = login.json()["auth_context"]
    assert client.cookies.get("tt_auth_context") == fingerprint
    context_cookie = next(c for c in client.cookies.jar if c.name == "tt_auth_context")
    assert not context_cookie.has_nonstandard_attr("HttpOnly")
    assert context_cookie.path == "/" and context_cookie.secure == settings.cookie_secure
    assert context.json() == {"auth_context": fingerprint}
    assert client.get("/api/auth/me").json()["auth_context"] == fingerprint
    assert context.headers["cache-control"] == "no-store"
    token = client.cookies.get(settings.cookie_name)
    stored_hash = db.scalar(select(UserSession.token_hash).where(UserSession.token_hash == token_digest(token)))
    assert stored_hash is not None
    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)
    assert fingerprint not in {token, stored_hash}


def test_context_from_form_login_is_available_in_me(client):
    form = client.post("/api/auth/login-form", data={"username": "ivanov", "password": "demo1234"},
                       follow_redirects=False)
    assert form.status_code == 303
    assert form.headers["location"] == "/"
    context = client.get("/api/auth/context")
    assert context.status_code == 200, context.text
    assert client.get("/api/auth/me").json()["auth_context"] == context.json()["auth_context"]
    assert client.cookies.get("tt_auth_context") == context.json()["auth_context"]


def test_password_change_returns_replacement_context(app_stack, admin_client):
    username = "password.context.test"
    created = admin_client.post("/api/employees", json={
        "full_name": "Смена Контекста", "username": username, "password": "demo1234", "role": "employee"})
    assert created.status_code == 200, created.text
    current = _login(app_stack, username)
    old = TestClient(app_stack["app"])
    old.cookies.set(settings.cookie_name, current.cookies.get(settings.cookie_name))
    before = current.get("/api/auth/context")
    replaced = current.post("/api/auth/change-password", json={
        "old_password": "demo1234", "new_password": "new-demo1234"})
    assert replaced.status_code == 200, replaced.text
    assert old.get("/api/auth/context").status_code == 401
    assert before.status_code == 200, before.text
    assert replaced.json()["ok"] is True
    after = replaced.json()["auth_context"]
    assert current.cookies.get("tt_auth_context") == after
    assert after != before.json()["auth_context"]
    assert current.get("/api/auth/context").json() == {"auth_context": after}


def test_logout_revokes_all_devices(app_stack, db):
    phone, laptop = _login(app_stack), _login(app_stack)
    assert phone.get("/api/auth/me").status_code == 200 and laptop.get("/api/auth/me").status_code == 200
    assert laptop.post("/api/auth/logout").status_code == 200
    assert laptop.cookies.get("tt_auth_context") == "signed-out"
    assert phone.get("/api/auth/me").status_code == 401
    user = db.scalar(select(User).where(User.username == "ivanov"))
    assert db.scalar(select(func.count()).select_from(UserSession).where(UserSession.user_id == user.id)) == 0


def test_impersonation_replaces_session(app_stack):
    admin = _login(app_stack, "admin")
    before = admin.cookies.get(settings.cookie_name)
    before_context = admin.get("/api/auth/context")
    emp = admin.get("/api/employees").json()
    target = next(e for e in emp if e.get("username") == "ivanov" or e.get("full_name", "").startswith("Иванов"))
    r = admin.post("/api/auth/impersonate", json={"employee_id": target["id"]})
    assert r.status_code == 200, r.text
    after = admin.cookies.get(settings.cookie_name)
    assert after != before
    old = TestClient(app_stack["app"])
    old.cookies.set(settings.cookie_name, before)
    assert old.get("/api/auth/me").status_code == 401, "прежняя сессия не должна жить рядом с «как сотрудник»"
    assert old.get("/api/auth/context").status_code == 401
    me = admin.get("/api/auth/me").json()
    assert me["user"]["impersonated"] is True
    stopped = admin.post("/api/auth/impersonate/stop")
    assert stopped.status_code == 200
    assert admin.get("/api/auth/me").json()["user"]["impersonated"] is False
    old.cookies.set(settings.cookie_name, after)
    assert old.get("/api/auth/context").status_code == 401
    assert before_context.status_code == 200, before_context.text
    assert r.json()["ok"] is True
    assert r.cookies.get("tt_auth_context") == r.json()["auth_context"]
    assert stopped.cookies.get("tt_auth_context") == stopped.json()["auth_context"]
    assert stopped.json()["ok"] is True
    assert me["auth_context"] == r.json()["auth_context"]
    assert len({before_context.json()["auth_context"], r.json()["auth_context"], stopped.json()["auth_context"]}) == 3
    assert admin.get("/api/auth/context").json() == {"auth_context": stopped.json()["auth_context"]}


def test_expired_sessions_are_purged_on_open(app_stack, db):
    user = db.scalar(select(User).where(User.username == "ivanov"))
    stale = open_session(db, user, user.employee_id)
    db.flush()
    row = db.scalar(select(UserSession).where(UserSession.token_hash == token_digest(stale)))
    row.expires_at = dt.datetime(2000, 1, 1, tzinfo=dt.UTC)
    db.commit()
    client = TestClient(app_stack["app"])
    client.cookies.set(settings.cookie_name, stale)
    assert client.get("/api/auth/context").status_code == 401
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
