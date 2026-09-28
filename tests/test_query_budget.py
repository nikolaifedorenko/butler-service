"""Стражи от регрессий N+1: бюджет SQL-запросов на горячих маршрутах.

Зачем: сборка сетки месяца и пересчёт диапазона исторически делали по три точечных
запроса на каждую ячейку (N сотрудников × 31 день) — 4 515 запросов на 50 сотрудниках.
После пакетной загрузки (ShiftCatalog, BlockIndex, DoubleContext, предзагрузка
периодов/ячеек/отметок) число запросов перестало зависеть от штата. Эти тесты
фиксируют такое поведение: если кто-то вернёт запрос внутрь цикла, тест упадёт.

Пороги намеренно свободные (в разы выше фактических значений), чтобы тест не
ломался от добавления ещё одного пакетного запроса, но ловил рост «на сотрудника».
"""
from __future__ import annotations

import datetime as dt

from app.deps import local_date

SCHEDULE_BUDGET = 40        # фактически ~13
ONWORK_BUDGET = 30          # фактически ~11
EMPLOYEES_BUDGET = 25       # фактически ~5


def _month(client) -> dict:
    today = local_date()
    return {"year": today.year, "month": today.month}


def test_schedule_grid_query_budget(manager_client, sql_counter):
    with sql_counter() as c:
        r = manager_client.get("/api/schedule", params=_month(manager_client))
    assert r.status_code == 200, r.text
    assert c["total"] <= SCHEDULE_BUDGET, (
        f"сетка месяца сделала {c['total']} запросов (бюджет {SCHEDULE_BUDGET}) — "
        f"похоже на N+1; топ запросов: {sorted(c['by_statement'].items(), key=lambda x: -x[1])[:3]}")


def test_onwork_query_budget(manager_client, sql_counter):
    with sql_counter() as c:
        r = manager_client.get("/api/punches/onwork")
    assert r.status_code == 200, r.text
    assert c["total"] <= ONWORK_BUDGET, (
        f"«Кто на работе» сделал {c['total']} запросов (бюджет {ONWORK_BUDGET}); "
        "раздел опрашивается каждые 30 с каждым открытым клиентом")


def test_employees_list_query_budget(manager_client, sql_counter):
    with sql_counter() as c:
        r = manager_client.get("/api/employees")
    assert r.status_code == 200, r.text
    assert c["total"] <= EMPLOYEES_BUDGET, (
        f"список сотрудников сделал {c['total']} запросов (бюджет {EMPLOYEES_BUDGET})")


def test_schedule_grid_does_not_scale_with_headcount(admin_client, db, sql_counter):
    """Главная проверка: рост штата НЕ должен умножать число запросов.

    Добавляем 12 сотрудников и сравниваем бюджет сетки: допустим небольшой рост
    (пакетные запросы те же), но не пропорциональный числу ячеек.
    """
    from app.models import Employee

    with sql_counter() as before:
        r1 = admin_client.get("/api/schedule", params=_month(admin_client))
    assert r1.status_code == 200, r1.text

    today = local_date()
    added = []
    for i in range(12):
        emp = Employee(full_name=f"Бюджетов Тест {i:02d}", short_name=f"Б.Тест{i}",
                       position="Батлер", schedule_group="Смена 1",
                       hired_at=today - dt.timedelta(days=400), active=True)
        db.add(emp)
        added.append(emp)
    db.commit()
    try:
        with sql_counter() as after:
            r2 = admin_client.get("/api/schedule", params=_month(admin_client))
        assert r2.status_code == 200, r2.text
        rows_before = len(r1.json()["rows"])
        rows_after = len(r2.json()["rows"])
        assert rows_after > rows_before, "новые сотрудники не попали в сетку — тест не проверяет масштабирование"
        growth = after["total"] - before["total"]
        assert after["total"] <= SCHEDULE_BUDGET, (
            f"после роста штата сетка делает {after['total']} запросов (бюджет {SCHEDULE_BUDGET})")
        assert growth <= 12, (
            f"число запросов выросло на {growth} при +12 сотрудниках — запросы снова "
            "считаются по каждому сотруднику/ячейке")
    finally:
        for emp in added:
            db.delete(emp)
        db.commit()


def test_recalc_month_query_budget(admin_client, sql_counter):
    """Пересчёт месяца: раньше ~12 000 операторов на 50 сотрудниках, теперь сотни.

    Порог сознательно считается от числа сотрудников: пересчёт legitimately делает
    по одному чтению строки табеля на пару «сотрудник × день», но НЕ по 10 запросов.
    """
    emps = admin_client.get("/api/employees").json()
    days = 31
    budget = 60 + len(emps) * days * 2      # запас: не более 2 операторов на ячейку
    params = _month(admin_client)
    with sql_counter() as c:
        r = admin_client.post("/api/settings/recalc-all", params=params)
    assert r.status_code == 200, r.text
    assert c["total"] <= budget, (
        f"пересчёт месяца сделал {c['total']} операторов при бюджете {budget} — "
        "похоже, в цикл вернулись точечные запросы")
