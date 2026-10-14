"""CSRF-защита и rate-limit входа.

CSRF в общем прогоне отключён (conftest ставит CSRF_ENABLED=0), потому что
TestClient не имитирует браузерную отправку cookie+заголовка. Здесь защита
включается точечно и проверяется, что mutating-запросы требуют пару
«cookie tt_csrf + заголовок X-CSRF-Token», а вход защищён от перебора.
"""
from __future__ import annotations


def test_csrf_requires_token_header(app_stack):
    from fastapi.testclient import TestClient

    from app.config import settings

    settings.csrf_enabled = True
    try:
        c = TestClient(app_stack["app"])
        r = c.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"})
        assert r.status_code == 200, r.text
        csrf = c.cookies.get("tt_csrf")
        assert csrf, "CSRF-cookie не выставлена при входе"

        # без заголовка — CSRF-отказ
        r = c.post("/api/punches", json={"kind": "auto"})
        assert r.status_code == 403
        assert "CSRF" in (r.json().get("detail") or "")

        # с неверным токеном — CSRF-отказ
        r = c.post("/api/punches", json={"kind": "auto"}, headers={"X-CSRF-Token": "bad"})
        assert r.status_code == 403

        # с верным токеном CSRF пройден: дальше — бизнес-логика (не CSRF)
        r = c.post("/api/punches", json={"kind": "auto"}, headers={"X-CSRF-Token": csrf})
        assert r.status_code in (200, 409)
    finally:
        settings.csrf_enabled = False


def test_login_rate_limit(app_stack):
    from fastapi.testclient import TestClient

    from app.api import auth_routes

    auth_routes._login_failures.clear()
    try:
        c = TestClient(app_stack["app"])
        for _ in range(auth_routes._LOGIN_MAX_ATTEMPTS):
            c.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        r = c.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 429
    finally:
        auth_routes._login_failures.clear()
