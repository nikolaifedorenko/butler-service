"""Самодиагностика схемы: /api/selfcheck обязан строиться из models.py.

Раньше список «обязательных» таблиц и колонок был рукописным и разошёлся с
migrate_db(): шесть добавленных миграцией колонок (включая users.token_version)
не проверялись. Теперь selfcheck берёт схему из Base.metadata, поэтому расходиться
нечему — эти тесты фиксируют такое поведение.
"""
from __future__ import annotations


def test_selfcheck_ok_na_svezhei_baze(admin_client):
    r = admin_client.get("/api/selfcheck")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True, f"схема не совпадает с моделями: {data['missing'][:10]}"
    assert data["missing"] == []
    assert data["hint"] == ""


def test_selfcheck_ozhidaet_vse_tablicy_iz_modealey(admin_client):
    from app.core.db import Base

    data = admin_client.get("/api/selfcheck").json()
    expected = {t.name for t in Base.metadata.sorted_tables}
    assert data["tables_expected"] == len(expected)
    assert data["tables_found"] == len(expected), \
        "в БД нет части таблиц, объявленных в models.py"
    assert len(expected) >= 30, "схема неожиданно уменьшилась — проверьте models.py"


def test_selfcheck_dostupen_bez_vhoda(client):
    """Самодиагностика намеренно не требует входа: её показывают в инструкции по установке.
    Но без входа отдаётся только итог — без перечня таблиц и колонок."""
    r = client.get("/api/selfcheck")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    for key in ("missing", "tables_expected", "tables_found"):
        assert key not in data, f"анониму не должна раскрываться схема БД ({key})"


def test_selfcheck_bez_detalei_dlya_ne_admina(employee_client):
    data = employee_client.get("/api/selfcheck").json()
    assert "missing" not in data


def test_migraciya_idempotentna(admin_client):
    """Повторный прогон migrate_db() не ломает схему и не падает.

    Миграция выполняется при каждом старте сервера, поэтому обязана быть идемпотентной:
    ALTER TABLE ADD COLUMN на уже существующую колонку недопустим.
    """
    from app.main import migrate_db

    migrate_db()          # второй раз поверх уже мигрированной базы
    migrate_db()          # и третий — для надёжности
    data = admin_client.get("/api/selfcheck").json()
    assert data["ok"] is True, f"после повторных миграций схема разошлась: {data['missing'][:10]}"
