"""Наблюдаемость (батч 15.10.2026): request-id, глубокий health, /metrics.

request-id должен возвращаться в ответе (сквозная трассировка с прокси),
health — сообщать версию и состояние БД (503, если БД недоступна), /metrics —
быть выключенным по умолчанию и включаться флагом METRICS_ENABLED.
"""
from __future__ import annotations


def test_request_id_roundtrip(app_stack):
    from fastapi.testclient import TestClient

    c = TestClient(app_stack["app"])
    # сгенерированный
    r = c.get("/api/health")
    rid = r.headers.get("x-request-id")
    assert rid and len(rid) >= 8
    # принятый от прокси — возвращается как есть (сквозная трассировка)
    r = c.get("/api/health", headers={"X-Request-ID": "proxy-rid-123"})
    assert r.headers.get("x-request-id") == "proxy-rid-123"
    # мусор в заголовке не проходит в ответ (защита от log-injection):
    # байт 0xE9 starlette декодирует как «é» — символ вне белого списка вырезается
    r = c.get("/api/health", headers={"X-Request-ID": b"bad id \xe9"})
    assert r.headers.get("x-request-id") == "badid"


def test_health_deep(app_stack):
    from fastapi.testclient import TestClient

    from app.core.config import settings

    c = TestClient(app_stack["app"])
    r = c.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["db"] == "ok"
    assert body["version"] == settings.app_version
    assert "server_time_utc" in body


def test_metrics_disabled_by_default(app_stack):
    from fastapi.testclient import TestClient

    c = TestClient(app_stack["app"])
    assert c.get("/metrics").status_code == 404


def test_metrics_enabled_by_flag(app_stack):
    from fastapi.testclient import TestClient

    from app.core.config import settings

    c = TestClient(app_stack["app"])
    settings.metrics_enabled = True
    try:
        c.get("/api/health")   # накручиваем счётчик
        r = c.get("/metrics")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        assert "tt_http_requests_total" in r.text
    finally:
        settings.metrics_enabled = False
