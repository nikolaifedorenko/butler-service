"""Стражи от регрессий N+1: бюджет SQL-запросов на горячих маршрутах.

Зачем: сборка сетки месяца и пересчёт диапазона исторически делали по три точечных
запроса на каждую ячейку (N сотрудников × 31 день) — 4 515 запросов на 50 сотрудниках.
После пакетной загрузки (ShiftCatalog, BlockIndex, предзагрузка
периодов/ячеек/отметок) число запросов перестало зависеть от штата. Эти тесты
фиксируют такое поведение: если кто-то вернёт запрос внутрь цикла, тест упадёт.

Пороги намеренно свободные (в разы выше фактических значений), чтобы тест не
ломался от добавления ещё одного пакетного запроса, но ловил рост «на сотрудника».
"""
from __future__ import annotations

import datetime as dt

import pytest

from app.core.time import local_date

SCHEDULE_BUDGET = 40        # сетка Графика: батч-запросы, не зависит от штата
BOARD_BUDGET = 20           # доска «Отметки»: 4 батч-порта + разрешение Settings (16.2)
EMPLOYEES_BUDGET = 25       # фактически ~5
MGMT_PER_EMPLOYEE = 40      # УТ: 6–8 запросов + конвейер на ОДНОГО сотрудника (16.1 п.5)
# PERF-02 (аудит, шаг 6.4): Табель и Факт за месяц — пакетно, не зависят от штата
TABEL_BUDGET = 60           # фактически 31 (было 96 и +6 на сотрудника)
FACT_MONTH_BUDGET = 50      # фактически 23 (было 64 и +4 на сотрудника)
# экраны без проверок до 6.4: фактические значения 8–16, рост штата их не меняет
FLAT_BUDGETS = {"/api/cars": 30, "/api/cars/meta": 20, "/api/settings": 35,
                "/api/audit": 20, "/api/engine-settings": 20}
GRID_BUDGETS = {"/api/schedule": SCHEDULE_BUDGET, "/api/tabel": TABEL_BUDGET,
                "/api/fact/month": FACT_MONTH_BUDGET}


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


def test_board_query_budget(manager_client, sql_counter):
    """Доска «Отметки» — константное число запросов (≤ 5 батч-источников, 16.1 п.4–5);
    разрешение Settings добавляет несколько точечных запросов версии/модификаторов."""
    with sql_counter() as c:
        r = manager_client.get("/api/presence/board")
    assert r.status_code == 200, r.text
    assert c["total"] <= BOARD_BUDGET, (
        f"доска сделала {c['total']} запросов (бюджет {BOARD_BUDGET}); "
        "раздел опрашивается каждые 30 с каждым открытым клиентом")


def test_employees_list_query_budget(manager_client, sql_counter):
    with sql_counter() as c:
        r = manager_client.get("/api/employees")
    assert r.status_code == 200, r.text
    assert c["total"] <= EMPLOYEES_BUDGET, (
        f"список сотрудников сделал {c['total']} запросов (бюджет {EMPLOYEES_BUDGET})")


@pytest.mark.parametrize("path", GRID_BUDGETS)
def test_month_grid_does_not_scale_with_headcount(admin_client, db, sql_counter, path):
    """Главная проверка: рост штата НЕ должен умножать число запросов.

    Добавляем 12 сотрудников и сравниваем бюджет сетки месяца (График, Табель, Факт):
    допустим небольшой рост (пакетные запросы те же), но не пропорциональный штату.
    """
    budget = GRID_BUDGETS[path]
    from app.modules.employees.application.catalog import Employee, EmploymentPeriod

    with sql_counter() as before:
        r1 = admin_client.get(path, params=_month(admin_client))
    assert r1.status_code == 200, r1.text

    today = local_date()
    added = []
    for i in range(12):
        emp = Employee(full_name=f"Бюджетов Тест {i:02d}", short_name=f"Б.Тест{i}",
                       position="Батлер", schedule_group="Смена 1",
                       hired_at=today - dt.timedelta(days=400), active=True)
        db.add(emp)
        db.flush()
        # период занятости, как при приёме через сервис (без него GET досоздаёт его каждый раз)
        db.add(EmploymentPeriod(employee_id=emp.id, start_date=emp.hired_at))
        added.append(emp)
    db.commit()
    try:
        with sql_counter() as after:
            r2 = admin_client.get(path, params=_month(admin_client))
        assert r2.status_code == 200, r2.text
        rows_before = len(r1.json()["rows"])
        rows_after = len(r2.json()["rows"])
        assert rows_after > rows_before, "новые сотрудники не попали в сетку — тест не проверяет масштабирование"
        growth = after["total"] - before["total"]
        assert after["total"] <= budget, (
            f"после роста штата {path} делает {after['total']} запросов (бюджет {budget})")
        # фактически 0: допуск — пара пакетных запросов, но не даже один запрос на сотрудника
        assert growth <= 3, (
            f"число запросов выросло на {growth} при +12 сотрудниках — запросы снова "
            "считаются по каждому сотруднику/ячейке")
    finally:
        db.query(EmploymentPeriod).filter(EmploymentPeriod.employee_id.in_([e.id for e in added])) \
            .delete(synchronize_session=False)
        for emp in added:
            db.delete(emp)
        db.commit()


def test_mgmt_view_query_budget(admin_client, sql_counter):
    """УТ месяца: тяжёлый конвейер — 6–8 запросов + расчёт НА ОДНОГО сотрудника (16.1 п.5),
    поэтому бюджет линейный по штату, но с малым коэффициентом."""
    with sql_counter() as c:
        r = admin_client.get("/api/mgmt", params=_month(admin_client))
    assert r.status_code == 200, r.text
    employees = max(1, len(r.json()["rows"]))
    budget = MGMT_PER_EMPLOYEE * employees + 20
    assert c["total"] <= budget, (
        f"УТ месяца сделал {c['total']} запросов на {employees} сотрудниках (бюджет {budget}); "
        f"топ: {sorted(c['by_statement'].items(), key=lambda x: -x[1])[:3]}")


NIGHT_ARCHIVE_BUDGET = 10   # PERF-01: было ~24 SQL на отчёт (ленивые области и пункты)


def test_night_archive_query_budget(manager_client, sql_counter):
    with sql_counter() as c:
        r = manager_client.get("/api/night/reports", params={"limit": 365})
    assert r.status_code == 200, r.text
    assert r.json()["reports"], "в демо-данных нет ночных отчётов — тест ничего не проверяет"
    assert c["total"] <= NIGHT_ARCHIVE_BUDGET, (
        f"архив ночи сделал {c['total']} запросов на {len(r.json()['reports'])} отчётов "
        f"(бюджет {NIGHT_ARCHIVE_BUDGET}) — похоже на N+1")


@pytest.mark.parametrize("path", FLAT_BUDGETS)
def test_screen_query_budget(manager_client, sql_counter, path):
    with sql_counter() as c:
        r = manager_client.get(path)
    assert r.status_code == 200, r.text
    assert c["total"] <= FLAT_BUDGETS[path], (
        f"{path} сделал {c['total']} запросов (бюджет {FLAT_BUDGETS[path]}); "
        f"топ: {sorted(c['by_statement'].items(), key=lambda x: -x[1])[:3]}")
