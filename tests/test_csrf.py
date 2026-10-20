"""CSRF-защита и rate-limit входа.

CSRF в общем прогоне отключён (conftest ставит CSRF_ENABLED=0), потому что
TestClient не имитирует браузерную отправку cookie+заголовка. Здесь защита
включается точечно и проверяется, что mutating-запросы требуют пару
«cookie tt_csrf + заголовок X-CSRF-Token», причём отклонённый запрос НЕ
производит побочных эффектов (токен проверяется до вызова обработчика),
а вход защищён от перебора.
"""
from __future__ import annotations


def _punch_count(app_stack) -> int:
    from app.modules.timesheet.application.catalog import Punch

    db = app_stack["SessionLocal"]()
    try:
        return db.query(Punch).count()
    finally:
        db.close()


def test_csrf_requires_token_header(app_stack):
    from fastapi.testclient import TestClient

    from app.core.config import settings

    settings.csrf_enabled = True
    try:
        c = TestClient(app_stack["app"])
        r = c.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"})
        assert r.status_code == 200, r.text
        csrf = c.cookies.get("tt_csrf")
        assert csrf, "CSRF-cookie не выставлена при входе"

        # без заголовка — CSRF-отказ, и он НЕ должен производить побочных эффектов:
        # отметка не создаётся (проверка токена выполняется до вызова обработчика)
        before = _punch_count(app_stack)
        r = c.post("/api/punches", json={"kind": "auto"})
        assert r.status_code == 403
        assert "CSRF" in (r.json().get("detail") or "")
        assert _punch_count(app_stack) == before, "отклонённый запрос выполнил действие"

        # с неверным токеном — CSRF-отказ, тоже без побочных эффектов
        r = c.post("/api/punches", json={"kind": "auto"}, headers={"X-CSRF-Token": "bad"})
        assert r.status_code == 403
        assert _punch_count(app_stack) == before, "отклонённый запрос выполнил действие"

        # не-ASCII заголовок — 403, а не 500: байт 0xE9 в сыром HTTP-запросе
        # starlette декодирует как «é», а compare_digest для str с не-ASCII бросает
        # TypeError — поэтому сравнение побайтовое (httpx str с не-ASCII не отправляет)
        r = c.post("/api/punches", json={"kind": "auto"},
                   headers={"X-CSRF-Token": b"\xe9"})
        assert r.status_code == 403
        assert _punch_count(app_stack) == before

        # с верным токеном CSRF пройден: дальше — бизнес-логика (не CSRF).
        # 409 допустим, если отметка за сегодня уже есть из других тестов прогона.
        r = c.post("/api/punches", json={"kind": "auto"}, headers={"X-CSRF-Token": csrf})
        assert r.status_code in (200, 409)
        if r.status_code == 200:
            assert _punch_count(app_stack) == before + 1
    finally:
        settings.csrf_enabled = False


def test_csrf_cookie_issued_on_denied_request(app_stack):
    """Первый mutating-запрос без cookie отклоняется, но cookie выдаётся —
    после обновления страницы клиент сможет повторить запрос с токеном."""
    from fastapi.testclient import TestClient

    from app.core.config import settings

    settings.csrf_enabled = True
    try:
        c = TestClient(app_stack["app"])
        r = c.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"})
        assert r.status_code == 200, r.text
        c.cookies.clear()   # имитация «cookie ещё нет» (первый визит/очистка)
        r = c.post("/api/punches", json={"kind": "auto"})
        assert r.status_code == 403
        assert c.cookies.get("tt_csrf"), "403-ответ не выставил CSRF-cookie"
    finally:
        settings.csrf_enabled = False


def test_login_rate_limit(app_stack):
    from fastapi.testclient import TestClient

    from app.modules.access.interface import auth_routes

    auth_routes._login_failures.clear()
    try:
        c = TestClient(app_stack["app"])
        for _ in range(auth_routes._LOGIN_MAX_ATTEMPTS):
            c.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        r = c.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 429
    finally:
        auth_routes._login_failures.clear()
