"""Страница печати (POST /api/docs/print): сервер собирает чистый HTML документ.

A1 (аудит 25.10.2026): прежняя печать писала inline-скрипт автопечати в about:blank —
окно наследует CSP приложения, ``script-src 'self'`` блокировал скрипт, кнопки
«Печать» молча не работали. Теперь страницу собирает сервер: автопечать — внешний
файл из SHELL, заголовок экранируется здесь, тело и стили клиент собирает
шаблонами lit-html (данные экранированы на месте).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings


def test_print_page_assembles_document(employee_client):
    r = employee_client.post("/api/docs/print", json={
        "title": "График <b>сменности</b>",
        "body": "<table><tr><td>Иванов</td></tr></table>",
        "css": ".x { color: red }"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "script-src 'self'" in r.headers["content-security-policy"].split("; ")
    html = r.text
    assert "<title>График &lt;b&gt;сменности&lt;/b&gt;</title>" in html   # заголовок экранирует сервер
    assert "<table><tr><td>Иванов</td></tr></table>" in html             # тело — как собрал клиент
    assert ".x { color: red }" in html
    assert '<script src="/static/js/print-page.js" defer></script>' in html  # автопечать — внешний скрипт
    assert "<script>" not in html and "onload=" not in html               # inline-скриптов нет


def test_print_page_requires_login(app_stack):
    client = TestClient(app_stack["app"])
    denied = client.post("/api/docs/print", json={"body": "x"})
    assert denied.status_code == 401
    assert "x-butler-auth-context" not in denied.headers
    assert client.get("/api/auth/context").status_code == 401


def test_print_header_reports_current_cookie_context(employee_client):
    response = employee_client.post("/api/docs/print", json={"body": "x"},
                                    headers={"X-Butler-Auth-Context": "a" * 64})
    assert response.status_code == 200
    context = employee_client.get("/api/auth/context")
    assert context.status_code == 200, context.text
    assert response.headers["x-butler-auth-context"] == context.json()["auth_context"]


def test_auth_context_cannot_authenticate_print_or_context(client, employee_client):
    context = employee_client.get("/api/auth/context")
    assert context.status_code == 200, context.text
    fingerprint = context.json()["auth_context"]
    headers = {"X-Butler-Auth-Context": fingerprint}
    client.cookies.set(settings.cookie_name, fingerprint)
    assert client.get("/api/auth/context", headers=headers).status_code == 401
    assert client.post("/api/docs/print", json={"body": "x"}, headers=headers).status_code == 401
