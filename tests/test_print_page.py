"""Страница печати (POST /api/docs/print): сервер собирает чистый HTML документ.

A1 (аудит 25.10.2026): прежняя печать писала inline-скрипт автопечати в about:blank —
окно наследует CSP приложения, ``script-src 'self'`` блокировал скрипт, кнопки
«Печать» молча не работали. Теперь страницу собирает сервер: автопечать — внешний
файл из SHELL, заголовок экранируется здесь, тело и стили клиент собирает
шаблонами lit-html (данные экранированы на месте).
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_print_page_assembles_document(employee_client):
    r = employee_client.post("/api/docs/print", json={
        "title": "График <b>сменности</b>",
        "body": "<table><tr><td>Иванов</td></tr></table>",
        "css": ".x { color: red }"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    html = r.text
    assert "<title>График &lt;b&gt;сменности&lt;/b&gt;</title>" in html   # заголовок экранирует сервер
    assert "<table><tr><td>Иванов</td></tr></table>" in html             # тело — как собрал клиент
    assert ".x { color: red }" in html
    assert '<script src="/static/js/print-page.js" defer></script>' in html  # автопечать — внешний скрипт
    assert "<script>" not in html and "onload=" not in html               # inline-скриптов нет


def test_print_page_requires_login(app_stack):
    assert TestClient(app_stack["app"]).post("/api/docs/print", json={"body": "x"}).status_code == 401
