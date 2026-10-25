"""Самодиагностика схемы: /api/selfcheck обязан строиться из models.py.

Раньше список «обязательных» таблиц и колонок был рукописным и разошёлся со схемой:
шесть добавленных колонок (включая users.token_version) не проверялись. Теперь selfcheck берёт схему из Base.metadata, поэтому расходиться
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


def test_selfcheck_vidit_propushchennyi_unikalnyi_indeks(admin_client, employee_client, db):
    """Миграции 0004/0009 при дублях в данных индекс пропускают (данные не трогают): защита
    «один сотрудник — один кар» не работает, а самопроверка раньше писала «в порядке».
    Теперь — ok=False, у администратора индекс с командой создания; команда рабочая."""
    from sqlalchemy import inspect, text

    from app.core.db import engine

    def has_index():
        return "ux_cars_assigned_to" in {i["name"] for i in inspect(engine).get_indexes("cars")}

    assert has_index()
    db.rollback()
    with engine.begin() as con:
        con.execute(text("DROP INDEX ux_cars_assigned_to"))
    try:
        data = admin_client.get("/api/selfcheck").json()
        assert data["ok"] is False and data["missing_indexes"] == 1
        row = next(m for m in data["missing"] if "ux_cars_assigned_to" in m)
        assert "cars: assigned_to" in row and "CREATE UNIQUE INDEX ux_cars_assigned_to" in row
        assert "защитные уникальные индексы" in data["hint"] and "0009" in data["hint"]
        # не-админ видит итог и подсказку, но не перечень
        other = employee_client.get("/api/selfcheck").json()
        assert other["ok"] is False and "missing" not in other and other["hint"] == data["hint"]
        # команда из перечня создаёт ровно тот индекс
        with engine.begin() as con:
            con.execute(text(row.split(" — ", 1)[1]))
        assert has_index() and admin_client.get("/api/selfcheck").json()["ok"] is True
    finally:
        if not has_index():
            with engine.begin() as con:
                con.execute(text("CREATE UNIQUE INDEX ux_cars_assigned_to ON cars (assigned_to) "
                                 "WHERE assigned_to IS NOT NULL"))
