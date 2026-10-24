"""Увольнение и удаление сотрудника завершают его сессии (рецензия аудита 22.10.2026, P2).

token_version рос только при смене пароля и роли. Пока сотрудник уволен, вход закрывает
is_active=False, но после повторного приёма в пределах срока жизни токена (48 ч) старая
cookie снова работала — например, на телефоне, оставленном коллеге.
"""
from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient


def _new_employee(admin_client, username: str) -> int:
    r = admin_client.post("/api/employees", json={
        "full_name": f"Сессиев {username}", "position": "Батлер (тест сессий)",
        "hired_at": (dt.date.today() - dt.timedelta(days=30)).isoformat(),
        "schedule_group": "Смена 1", "role": "employee", "username": username,
        "password": "demo1234"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _session(app_stack, username: str) -> TestClient:
    c = TestClient(app_stack["app"])
    assert c.post("/api/auth/login", json={"username": username, "password": "demo1234"}).status_code == 200
    assert c.get("/api/auth/me").status_code == 200
    return c


def test_dismiss_then_rehire_does_not_revive_old_session(app_stack, admin_client):
    emp_id = _new_employee(admin_client, "sess_dismiss")
    old = _session(app_stack, "sess_dismiss")
    assert admin_client.post(f"/api/employees/{emp_id}/dismiss",
                             json={"date": dt.date.today().isoformat()}).status_code == 200
    r = admin_client.post(f"/api/employees/{emp_id}/rehire",
                          json={"date": (dt.date.today() + dt.timedelta(days=1)).isoformat()})
    assert r.status_code == 200, r.text
    assert old.get("/api/auth/me").status_code == 401, "сессия до увольнения ожила после приёма"
    _session(app_stack, "sess_dismiss")                  # новый вход — работает


def test_delete_ends_sessions(app_stack, admin_client, db):
    from app.core.identity import User

    emp_id = _new_employee(admin_client, "sess_delete")
    _session(app_stack, "sess_delete")
    user = db.query(User).filter(User.username == "sess_delete").one()
    before = int(user.token_version or 0)
    assert admin_client.post(f"/api/employees/{emp_id}/delete").status_code == 200
    db.expire_all()
    assert int(db.get(User, user.id).token_version or 0) == before + 1
