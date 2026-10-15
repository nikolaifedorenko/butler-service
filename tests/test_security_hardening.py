"""Безопасность, батч 15.10.2026: параметры хешей и ленивый rehash, заголовки
(CSP/HSTS/Permissions-Policy), демо-вход по умолчанию выключен, X-Forwarded-For
читается только за доверенным прокси.

Механизмы проверяются точечно: общий прогон (conftest) не имитирует браузер и
использует демо-флаги, поэтому здесь нужные настройки включаются/выключаются
вручную с восстановлением в finally.
"""
from __future__ import annotations

import hashlib


def test_password_hash_current_params():
    from app.security import _ITERATIONS, hash_password, needs_rehash

    assert _ITERATIONS >= 600_000, "OWASP: PBKDF2-SHA256 не ниже 600 000 итераций"
    h = hash_password("x")
    assert h.startswith(f"pbkdf2${_ITERATIONS}$")
    assert not needs_rehash(h)
    # старый хеш (120k) и мусор — требуют обновления
    assert needs_rehash("pbkdf2$120000$" + "00" * 16 + "$" + "ab" * 32)
    assert needs_rehash("garbage")


def test_login_rehashes_legacy_password(app_stack):
    """Успешный вход с хешем старых параметров прозрачно обновляет его до текущих."""
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.models import User
    from app.security import _ITERATIONS

    salt = "11" * 16
    digest = hashlib.pbkdf2_hmac("sha256", b"demo1234", salt.encode(), 120_000).hex()
    db = app_stack["SessionLocal"]()
    try:
        user = db.scalar(select(User).where(User.username == "ivanov"))
        user.password_hash = f"pbkdf2$120000${salt}${digest}"
        db.commit()
    finally:
        db.close()

    c = TestClient(app_stack["app"])
    r = c.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"})
    assert r.status_code == 200, r.text

    db = app_stack["SessionLocal"]()
    try:
        user = db.scalar(select(User).where(User.username == "ivanov"))
        assert user.password_hash.startswith(f"pbkdf2${_ITERATIONS}$"), \
            "хеш не обновлён при входе"
        # повторный вход с новым хешем тоже успешен
    finally:
        db.close()
    assert c.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"}).status_code == 200


def test_security_headers_present(app_stack):
    from fastapi.testclient import TestClient

    c = TestClient(app_stack["app"])
    r = c.get("/api/health")
    assert r.status_code == 200
    h = {k.lower(): v for k, v in r.headers.items()}
    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("x-frame-options") == "DENY"
    assert "geolocation=()" in h.get("permissions-policy", "")
    csp = h.get("content-security-policy", "")
    assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp.split(";")[1]
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp


def test_csp_report_only_toggle(app_stack):
    from fastapi.testclient import TestClient

    from app.config import settings

    c = TestClient(app_stack["app"])
    settings.csp_report_only = True
    try:
        h = {k.lower() for k in c.get("/api/health").headers}
        assert "content-security-policy-report-only" in h
        assert "content-security-policy" not in h
    finally:
        settings.csp_report_only = False


def test_hsts_only_over_https(app_stack):
    from fastapi.testclient import TestClient

    from app.config import settings

    c = TestClient(app_stack["app"])
    assert "strict-transport-security" not in c.get("/api/health").headers
    # за доверенным прокси (TRUST_PROXY_HEADERS=1) схема берётся из X-Forwarded-Proto
    settings.trust_proxy_headers = True
    try:
        r = c.get("/api/health", headers={"X-Forwarded-Proto": "https"})
        assert r.headers.get("strict-transport-security", "").startswith("max-age=")
        # без доверия к прокси тот же заголовок игнорируется
        settings.trust_proxy_headers = False
        r = c.get("/api/health", headers={"X-Forwarded-Proto": "https"})
        assert "strict-transport-security" not in r.headers
    finally:
        settings.trust_proxy_headers = False


def test_impersonation_flag_respected(app_stack):
    """Демо-вход «как сотрудник» управляется флагом; боевой default — выключен."""
    from fastapi.testclient import TestClient

    from app.config import Settings, settings

    assert Settings.model_fields["allow_impersonation"].default is False, \
        "в production демо-вход должен быть выключен по умолчанию"

    c = TestClient(app_stack["app"])
    assert c.post("/api/auth/login", json={"username": "gromova", "password": "demo1234"}).status_code == 200
    settings.allow_impersonation = False
    try:
        r = c.post("/api/auth/impersonate", json={"employee_id": 1})
        assert r.status_code == 403
    finally:
        settings.allow_impersonation = True


def test_client_ip_xff_only_when_trusted(app_stack):
    from types import SimpleNamespace

    from app.api.auth_routes import _client_ip
    from app.config import settings

    req = SimpleNamespace(headers={"x-forwarded-for": "1.2.3.4"},
                          client=SimpleNamespace(host="9.9.9.9"))
    settings.trust_proxy_headers = False
    try:
        assert _client_ip(req) == "9.9.9.9", "без доверия к прокси XFF игнорируется"
        settings.trust_proxy_headers = True
        assert _client_ip(req) == "1.2.3.4"
    finally:
        settings.trust_proxy_headers = False
