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


def _clear_login_attempts(app_stack) -> None:
    from sqlalchemy import delete

    from app.core.identity import LoginAttempt

    with app_stack["SessionLocal"]() as s:
        s.execute(delete(LoginAttempt))
        s.commit()


def test_login_rate_limit(app_stack):
    from fastapi.testclient import TestClient

    from app.modules.access.interface import auth_routes

    _clear_login_attempts(app_stack)
    try:
        c = TestClient(app_stack["app"])
        for _ in range(auth_routes._LOGIN_MAX_ATTEMPTS):
            c.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        r = c.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 429
    finally:
        _clear_login_attempts(app_stack)


def test_login_rate_limit_is_shared_between_workers(app_stack):
    """ADR-0005 (пересмотрен 22.10.2026): неудачи, записанные другим воркером или контейнером
    (здесь — прямо в таблицу), считаются в общий лимит; старше окна — не считаются."""
    import datetime as dt

    from fastapi.testclient import TestClient

    from app.core.identity import LoginAttempt
    from app.core.time import utcnow
    from app.modules.access.interface import auth_routes

    _clear_login_attempts(app_stack)
    try:
        c = TestClient(app_stack["app"])      # адрес клиента TestClient — «testclient»
        old = utcnow() - dt.timedelta(seconds=auth_routes._LOGIN_WINDOW_SECONDS + 60)
        with app_stack["SessionLocal"]() as s:
            s.add_all([LoginAttempt(key=auth_routes._attempt_key("testclient", "admin"), ts=old)
                       for _ in range(auth_routes._LOGIN_MAX_ATTEMPTS)])
            s.commit()
        assert c.post("/api/auth/login", json={"username": "admin", "password": "demo1234"}).status_code == 200
        with app_stack["SessionLocal"]() as s:
            s.add_all([LoginAttempt(key=auth_routes._attempt_key("testclient", "admin"))
                       for _ in range(auth_routes._LOGIN_MAX_ATTEMPTS)])
            s.commit()
        r = c.post("/api/auth/login", json={"username": "admin", "password": "demo1234"})
        assert r.status_code == 429, r.text
    finally:
        _clear_login_attempts(app_stack)


def test_own_login_does_not_reset_others_failures(app_stack):
    """Аудит 22.10.2026: свой успешный вход сбрасывал счётчик всего адреса — сотрудник
    перебирал пароль администратора без остановки. Теперь счётчик на пару «адрес + логин»."""
    from fastapi.testclient import TestClient

    from app.modules.access.interface import auth_routes

    _clear_login_attempts(app_stack)
    try:
        c = TestClient(app_stack["app"])
        for _ in range(auth_routes._LOGIN_MAX_ATTEMPTS - 1):
            c.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert c.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"}).status_code == 200
        c.post("/api/auth/login", json={"username": "admin", "password": "wrong"})       # десятая
        assert c.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 429
        # чужие ошибки с того же адреса не блокируют вход другим сотрудникам
        assert c.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"}).status_code == 200
    finally:
        _clear_login_attempts(app_stack)


def test_spray_over_many_logins_hits_ip_limit(app_stack):
    """Перебор по разным логинам с одного адреса упирается в общий потолок адреса."""
    from fastapi.testclient import TestClient

    from app.core.identity import LoginAttempt
    from app.modules.access.interface import auth_routes

    _clear_login_attempts(app_stack)
    try:
        with app_stack["SessionLocal"]() as s:
            s.add_all([LoginAttempt(key=auth_routes._attempt_key("testclient", f"user{i}"))
                       for i in range(auth_routes._LOGIN_MAX_PER_IP)])
            s.commit()
        r = TestClient(app_stack["app"]).post("/api/auth/login",
                                             json={"username": "admin", "password": "demo1234"})
        assert r.status_code == 429, r.text
    finally:
        _clear_login_attempts(app_stack)
