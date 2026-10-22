"""Быстрые правки безопасности (аудит 15.10.2026):

1. logout отзывает сессию на сервере (token_version), а не только удаляет cookie;
2. цвета (должность, тип смены) — только #rgb/#rrggbb: они попадают в style=…;
3. стартовая миграция v7.1 больше не очищает расчётные таблицы;
4. /api/selfcheck без входа не раскрывает схему БД (покрыто в test_selfcheck.py).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEMO_PASSWORD


def _login(app, username: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return c


# ── 1. logout ────────────────────────────────────────────────────────────────

def test_logout_otzyvaet_skopirovannuyu_cookie(app_stack, admin_client):
    """Отдельный пользователь: logout отзывает ВСЕ сессии пользователя, и общий
    демо-логин сломал бы сессии других тестов."""
    from app.core.config import settings

    r = admin_client.post("/api/employees", json={
        "full_name": "Выходов Тест Тестович", "username": "logout.test",
        "password": DEMO_PASSWORD, "role": "employee"})
    assert r.status_code == 200, r.text
    c = _login(app_stack["app"], "logout.test")
    stolen = c.cookies.get(settings.cookie_name)
    assert c.get("/api/auth/me").status_code == 200
    assert c.post("/api/auth/logout").status_code == 200

    attacker = TestClient(app_stack["app"])
    attacker.cookies.set(settings.cookie_name, stolen)
    assert attacker.get("/api/auth/me").status_code == 401, \
        "после выхода скопированная cookie не должна работать"
    # повторный вход выдаёт новую рабочую сессию
    assert _login(app_stack["app"], "logout.test").get("/api/auth/me").status_code == 200


def test_srok_sessii_po_umolchaniyu_ne_bolee_48_chasov():
    from app.core.config import Settings

    assert Settings.model_fields["session_ttl_hours"].default <= 48


# ── 2. цвета ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ['red"><a href=//evil>x</a>', "url(//evil/x.png)",
                                 "#12345", "#gggggg", "javascript:alert(1)"])
def test_cvet_dolzhnosti_tolko_hex(admin_client, bad):
    r = admin_client.post("/api/employees", json={"full_name": "Цветов Тест Тестович",
                                                  "group_color": bad})
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("bad", ['#fff" onmouseover="x', "blue;background:url(//e)"])
def test_cvet_tipa_smeny_tolko_hex(admin_client, bad):
    r = admin_client.post("/api/shift-types", json={"code": "ZZ_BAD", "name": "x", "color": bad})
    assert r.status_code == 422, r.text


def test_normalize_hex_color():
    from app.core.format import normalize_hex_color

    assert normalize_hex_color("#ABCDEF", "#000") == "#abcdef"
    assert normalize_hex_color("#abc", "#000") == "#abc"
    assert normalize_hex_color("", "#8a94a6") == "#8a94a6"
    assert normalize_hex_color(None, "#8a94a6") == "#8a94a6"
    with pytest.raises(ValueError):
        normalize_hex_color("red", "#000")


# ── 3. миграция без автоочистки ──────────────────────────────────────────────

def test_migraciya_v7_ne_udalyaet_dannye_bez_markera(app_stack):
    """Восстановили бэкап без маркера engine_v7_reset → данные Табеля обязаны уцелеть."""
    from sqlalchemy import func, select, text

    from app.bootstrap.migrations import migrate_engine_v7
    from app.core.db import engine
    from app.modules.timesheet.application.catalog import TabelDay

    S = app_stack["SessionLocal"]
    with S() as db:
        before = db.scalar(select(func.count()).select_from(TabelDay))
    assert before > 0, "в демо-базе ожидаются строки Табеля"
    with engine.begin() as con:
        con.execute(text("DELETE FROM settings WHERE key = 'engine_v7_reset'"))
    migrate_engine_v7()
    with S() as db:
        after = db.scalar(select(func.count()).select_from(TabelDay))
    assert after == before, "миграция на старте не должна удалять расчётные данные"
