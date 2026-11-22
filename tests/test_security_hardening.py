"""Безопасность, батч 15.10.2026: параметры хешей и ленивый rehash, заголовки
(CSP/HSTS/Permissions-Policy), демо-вход управляется флагом (включён по решению
владельца), X-Forwarded-For читается только за доверенным прокси.

Механизмы проверяются точечно: общий прогон (conftest) не имитирует браузер и
использует демо-флаги, поэтому здесь нужные настройки включаются/выключаются
вручную с восстановлением в finally.
"""
from __future__ import annotations


def test_password_hash_is_argon2id():
    from argon2 import PasswordHasher

    from app.core.security import hash_password, needs_rehash, verify_password

    h = hash_password("x")
    assert h.startswith("$argon2id$")
    assert verify_password("x", h) and not verify_password("y", h)
    assert not needs_rehash(h)
    # слабее текущих параметров и чужой формат — требуют обновления; чужой формат не проходит проверку
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("x")
    assert needs_rehash(weak) and needs_rehash("garbage")
    assert not verify_password("x", "pbkdf2$600000$" + "00" * 16 + "$" + "ab" * 32)
    assert not verify_password("x", "garbage")


def test_login_rehashes_weak_password(app_stack):
    """Успешный вход с хешем более слабых параметров прозрачно обновляет его до текущих."""
    from argon2 import PasswordHasher
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.core.identity import User
    from app.core.security import needs_rehash

    db = app_stack["SessionLocal"]()
    try:
        user = db.scalar(select(User).where(User.username == "ivanov"))
        user.password_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("demo1234")
        db.commit()
    finally:
        db.close()

    c = TestClient(app_stack["app"])
    r = c.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"})
    assert r.status_code == 200, r.text

    db = app_stack["SessionLocal"]()
    try:
        user = db.scalar(select(User).where(User.username == "ivanov"))
        assert not needs_rehash(user.password_hash), "хеш не обновлён при входе"
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

    from app.core.config import settings

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

    from app.core.config import settings

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
    """Демо-вход «как сотрудник»: включён по умолчанию (решение владельца
    15.10.2026), при ALLOW_IMPERSONATION=0 маршрут отдаёт 403."""
    from fastapi.testclient import TestClient

    from app.core.config import Settings, settings

    assert Settings.model_fields["allow_impersonation"].default is True, \
        "демо-вход нужен по умолчанию (решение владельца 15.10.2026)"

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

    from app.core.config import settings
    from app.core.net import client_ip as _client_ip

    req = SimpleNamespace(headers={"x-forwarded-for": "1.2.3.4"},
                          client=SimpleNamespace(host="9.9.9.9"))
    settings.trust_proxy_headers = False
    try:
        assert _client_ip(req) == "9.9.9.9", "без доверия к прокси XFF игнорируется"
        settings.trust_proxy_headers = True
        assert _client_ip(req) == "1.2.3.4"
        # левый адрес присылает клиент, правый дописывает nginx: подмена не обходит лимит
        req.headers["x-forwarded-for"] = "6.6.6.6, 1.2.3.4"
        assert _client_ip(req) == "1.2.3.4"
    finally:
        settings.trust_proxy_headers = False


def test_client_ip_is_a_valid_address_or_connection_peer(app_stack):
    """Адрес из XFF — только настоящий IP: «%», «_» и мусор попадали в LIKE лимита входа
    (чужой бакет), длинная строка — в ключ String(80) (500 на PostgreSQL). Рецензия 22.10.2026."""
    from types import SimpleNamespace

    from app.core.config import settings
    from app.core.net import client_ip
    from app.modules.access.application.auth import attempt_key as _attempt_key

    def ip(xff):
        return client_ip(SimpleNamespace(headers={"x-forwarded-for": xff},
                                         client=SimpleNamespace(host="9.9.9.9")))

    settings.trust_proxy_headers = True
    try:
        assert ip("6.6.6.6, 10.0.0.%") == "9.9.9.9"          # не IP — адрес соединения
        assert ip("1.2.3.4, " + "x" * 500) == "9.9.9.9"
        assert ip("fe80::1%eth0") == "fe80::1"               # зона IPv6 — не часть адреса
        assert ip("2001:DB8::1") == "2001:db8::1"            # одна запись на адрес
        longest = "ffff:ffff:ffff:ffff:ffff:ffff:255.255.255.255"
        assert len(_attempt_key(ip(longest), "u" * 200)) <= 80
    finally:
        settings.trust_proxy_headers = False


def test_prod_uvicorn_does_not_trust_any_proxy():
    """--forwarded-allow-ips "*": при TRUST_PROXY_HEADERS=0 uvicorn сам подставлял клиенту
    ЛЕВЫЙ адрес X-Forwarded-For (его присылает клиент) — лимит входа снова обходился."""
    import pathlib

    compose = (pathlib.Path(__file__).resolve().parents[1] / "docker-compose.prod.yml").read_text()
    code = "\n".join(line.split("#", 1)[0] for line in compose.splitlines())   # без комментариев
    assert "forwarded-allow-ips" not in code
    assert "--no-proxy-headers" in code


def test_backup_container_runs_not_as_root():
    """Остаток аудита 25.10.2026 (C2): backup-контейнер — единственный с секретами
    (закрытый ключ SSH, ключ age) — работает не от root; ключ SSH копируется
    entrypoint'ом в домашний каталог с правами 600 (ssh отказывается читать
    смонтированный файл чужого владельца)."""
    import pathlib

    deploy = pathlib.Path(__file__).resolve().parents[1] / "deploy"
    dockerfile = (deploy / "backup.Dockerfile").read_text(encoding="utf-8")
    entrypoint = (deploy / "backup-entrypoint.sh").read_text(encoding="utf-8")
    script = (deploy / "backup.sh").read_text(encoding="utf-8")
    assert "\nUSER " in dockerfile + "\n" and "USER root" not in dockerfile, \
        "backup.Dockerfile не переключает не-root пользователя"
    assert "adduser" in dockerfile and "id_ed25519" in entrypoint \
        and 'chmod 600 "$HOME/.ssh/id_ed25519"' in entrypoint, \
        "entrypoint не готовит закрытый ключ SSH для не-root пользователя"
    assert 'SSH_DIR="$HOME/.ssh"' in script, "backup.sh читает ключ не из домашнего каталога"
    compose = (pathlib.Path(__file__).resolve().parents[1] / "docker-compose.prod.yml").read_text()
    backup_block = compose.split("backup:", 1)[1].split("\n\n", 1)[0]
    assert "user:" not in backup_block, "compose подменяет пользователя образа"
