"""Двойная оплата (аудит, шаг 6.3, ARCH-03): то, что определяет деньги.

* Адаптер настроек превращает день календаря в модификатор «Двойные переработки» для групп
  графиков своего списка (сменные / пятидневка / все), а ВИП-период — для одного сотрудника
  и только в пределах периода расчёта.
* API календаря и ВИП-периодов: разбор дат, период с фильтром по дням недели, обновление
  существующего дня и все отказы 404/422.

Даты — в 2031 году: демо-данные и другие тесты туда не заходят.
"""
from __future__ import annotations

import datetime as dt

import pytest

D = dt.date


@pytest.fixture()
def calendar_rows(db):
    """День каждого списка и ВИП-период сотрудника, выходящий за границы периода."""
    from app.modules.employees.application import Employee
    from app.modules.timesheet.adapters.orm import DoublePayDay, VipDoublePay

    emp = db.query(Employee).filter(Employee.deleted_at.is_(None)).first()
    rows = [DoublePayDay(date=D(2031, 3, 2), scope="shift"),
            DoublePayDay(date=D(2031, 3, 3), scope="week5"),
            DoublePayDay(date=D(2031, 3, 4), scope="all"),
            VipDoublePay(employee_id=emp.id, start_date=D(2031, 2, 25), end_date=D(2031, 3, 5))]
    db.add_all(rows)
    db.commit()
    yield emp
    for r in rows:
        db.delete(r)
    db.commit()


def test_calendar_and_vip_become_double_overtime_modifiers(db, calendar_rows):
    from app.modules.timesheet.adapters.sql_settings import _modifier_rows
    from app.modules.timesheet.domain.settings.types import MOD_DOUBLE
    from app.modules.timesheet.domain.types.entities import Period

    rows = [r for r in _modifier_rows(db, Period(D(2031, 3, 1), D(2031, 3, 31)), "month")
            if r["name"] == MOD_DOUBLE]
    by_day = {}
    for r in rows:
        if r["day"]:
            by_day.setdefault(r["day"], set()).add(r["group"])
    assert by_day == {"2031-03-02": {"Смена 1", "Смена 2", "Другие смены"},
                      "2031-03-03": {"Пятидневка"},
                      "2031-03-04": {None}}
    vip = [r for r in rows if r["employee_id"] is not None]
    # ВИП-период обрезан периодом расчёта: февральские дни в мартовский расчёт не попадают
    assert vip == [{"name": MOD_DOUBLE, "value": "1", "employee_id": calendar_rows.id, "group": None,
                    "day": None, "period_start": "2031-03-01", "period_end": "2031-03-05"}]


def test_days_api_period_weekdays_update_and_delete(admin_client):
    # все субботы марта 2031 (1, 8, 15, 22, 29) + отдельная дата другим форматом
    r = admin_client.post("/api/doublepay/days", json={
        "start": "2031-03-01", "end": "31.03.2031", "weekdays": [5], "dates": "02.04.2031",
        "scope": "week5", "note": "праздники"})
    assert r.status_code == 200, r.text
    assert (r.json()["added"], r.json()["updated"]) == (6, 0)
    # повтор той же даты обновляет scope и примечание, а не дублирует день
    r = admin_client.post("/api/doublepay/days", json={"dates": "2031-03-01", "scope": "all"})
    assert (r.json()["added"], r.json()["updated"]) == (0, 1)
    days = admin_client.get("/api/doublepay", params={"year": 2031}).json()["days"]
    assert [d["date"] for d in days] == ["2031-03-01", "2031-03-08", "2031-03-15", "2031-03-22",
                                         "2031-03-29", "2031-04-02"]
    assert days[0]["scope"] == "all" and days[1]["scope"] == "week5" and days[1]["note"] == "праздники"
    for d in days:
        assert admin_client.delete(f"/api/doublepay/days/{d['id']}").status_code == 200
    assert admin_client.get("/api/doublepay", params={"year": 2031}).json()["days"] == []
    assert admin_client.delete(f"/api/doublepay/days/{days[0]['id']}").status_code == 404


@pytest.mark.parametrize("body", [
    {"dates": "2031-03-01", "scope": "weekend"},                    # неизвестный список
    {"dates": "2031-03-01 завтра"},                                  # нераспознанная дата
    {"start": "2031-03-01"},                                         # период без конца
    {"start": "2031-03-10", "end": "2031-03-01"},                    # конец раньше начала
    {"start": "2031-01-01", "end": "2034-12-31"},                    # больше ~3 лет
    {"dates": " , ;"},                                               # ни одной даты
])
def test_days_api_rejects_bad_input(admin_client, body):
    assert admin_client.post("/api/doublepay/days", json=body).status_code == 422


def test_vip_api_add_list_delete(admin_client, db, calendar_rows):
    emp = calendar_rows
    r = admin_client.post("/api/doublepay/vip", json={
        "employee_id": emp.id, "start_date": "10.06.2031", "end_date": "2031-06-20", "note": "ВИП"})
    assert r.status_code == 200, r.text
    item = r.json()["item"]
    assert (item["start_date"], item["end_date"], item["days"]) == ("2031-06-10", "2031-06-20", 11)
    assert item["employee_name"] == emp.display_name and item["author"]
    listed = admin_client.get("/api/doublepay", params={"year": 2031}).json()["vip"]
    assert {v["id"] for v in listed} >= {item["id"]}
    assert admin_client.delete(f"/api/doublepay/vip/{item['id']}").status_code == 200
    assert admin_client.delete(f"/api/doublepay/vip/{item['id']}").status_code == 404


@pytest.mark.parametrize("dates,status", [
    (("2031-06-10", "июнь"), 422),            # нераспознанная дата
    (("2031-06-20", "2031-06-10"), 422),      # конец раньше начала
    (("2031-01-01", "2032-06-01"), 422),      # длиннее года
])
def test_vip_api_rejects_bad_input(admin_client, calendar_rows, dates, status):
    r = admin_client.post("/api/doublepay/vip", json={
        "employee_id": calendar_rows.id, "start_date": dates[0], "end_date": dates[1]})
    assert r.status_code == status


def test_vip_api_unknown_employee_404(admin_client):
    r = admin_client.post("/api/doublepay/vip", json={
        "employee_id": 10**9, "start_date": "2031-06-10", "end_date": "2031-06-11"})
    assert r.status_code == 404
