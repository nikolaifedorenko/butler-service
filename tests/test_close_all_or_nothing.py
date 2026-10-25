"""Закрытие и пересчёт периода — «всё или ничего» по штату (решение владельца 25.10.2026).

Период закрывается сразу у всего штата. Раньше «Закрыть месяц» закрывал каждого своей
транзакцией и пропускал тех, у кого ошибка: месяц оказывался закрыт у части людей, а
индикатор настроек считал его закрытым. Теперь сначала предпроверка всех; хоть одна
ошибка — не закрываем никого и отдаём полный список. Выбрать сотрудников нельзя.

«Штат периода» в тестах — три своих сотрудника (подмена period_employees): тестовая база
общая на прогон, и сотрудники других тестов заблокировали бы закрытие.

Что проверяется:
  * один сотрудник с ошибкой — не закрыт никто, в ответе полный список;
  * после исправления закрываются все; уже закрытые пропускаются (докрытие);
  * пересчёт: у одного период не закрыт — не пересчитан никто;
  * employee_ids в запросе — 422;
  * индикатор настроек: «закрыт у N из M» со списком тех, у кого не закрыт.
"""
from __future__ import annotations

import calendar
import datetime as dt

import pytest
from sqlalchemy import select

from app.core.time import local_date

TODAY = local_date()
PREV = (TODAY.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
DAYS = [dt.date(PREV.year, PREV.month, d).isoformat()
        for d in range(1, calendar.monthrange(PREV.year, PREV.month)[1] + 1)]
BODY = {"year": PREV.year, "month": PREV.month}


def _hire(admin, name: str, tabel: bool) -> int:
    """Принят 1-го числа прошлого месяца, начальный банк посеян; tabel=False — Табель пуст."""
    r = admin.post("/api/employees", json={"full_name": name, "position": "Батлер",
                                           "hired_at": PREV.isoformat(), "schedule_group": "Смена 1"})
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    assert admin.post(f"/api/employees/{eid}/bank-adjust", json={
        "hours": 0, "date": PREV.isoformat(), "note": "посев", "reason_code": "OPENING_SEED"}).status_code == 200
    if tabel:
        _fill(admin, eid)
    return eid


def _fill(admin, eid: int) -> None:
    assert admin.post("/api/tabel/bulk", json={"employee_ids": [eid], "dates": DAYS,
                                               "code": "В"}).status_code == 200


@pytest.fixture
def staff(admin_client, db, monkeypatch):
    """Штат периода: Аккуратов и Порядков с Табелем, Пропусков — без Табеля."""
    from app.modules.employees.application import Employee
    from app.modules.timesheet.interface import mgmt_api

    ids = {"ok1": _hire(admin_client, "Аккуратов Тест Закрытия", True),
           "ok2": _hire(admin_client, "Порядков Тест Закрытия", True),
           "bad": _hire(admin_client, "Пропусков Тест Закрытия", False)}

    def period_employees(session, first, last, only=None):
        return list(session.scalars(select(Employee).where(Employee.id.in_(ids.values()))
                                    .order_by(Employee.id)))

    monkeypatch.setattr(mgmt_api, "period_employees", period_employees)
    yield ids
    for eid in ids.values():          # удалённые не попадают в штат следующих тестов
        admin_client.post(f"/api/employees/{eid}/delete")


def _closed(admin, eid: int) -> bool:
    r = admin.get("/api/mgmt", params={**BODY, "employee_id": eid})
    assert r.status_code == 200, r.text
    return r.json()["rows"][0]["state"]["closed"]


def test_one_error_blocks_everyone(admin_client, staff):
    r = admin_client.post("/api/mgmt/close", json=BODY)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is False and out["stage"] == "check" and out["done"] == []
    assert [e["employee_id"] for e in out["errors"]] == [staff["bad"]]
    assert "Пропусков" in out["errors"][0]["name"] and out["errors"][0]["error"]
    assert not _closed(admin_client, staff["ok1"]) and not _closed(admin_client, staff["ok2"])

    _fill(admin_client, staff["bad"])                       # исправили — закрываются все
    out = admin_client.post("/api/mgmt/close", json=BODY).json()
    assert out["ok"] is True and out["stage"] == "save" and out["errors"] == []
    assert sorted(d["employee_id"] for d in out["done"]) == sorted(staff.values())
    assert all(_closed(admin_client, eid) for eid in staff.values())

    again = admin_client.post("/api/mgmt/close", json=BODY).json()  # закрыт у всех
    assert again["ok"] is True and again["done"] == [] and again["skipped_closed"] == 3


def test_partially_closed_period_is_completed(admin_client, staff):
    """Период, закрытый частично (прежние правила, сбой посреди закрытия): «Закрыть»
    докрывает оставшихся, уже закрытых пропускает."""
    from tests.period_ops import period_action

    assert period_action("close", staff["ok1"], PREV.year, PREV.month)["errors"] == []
    _fill(admin_client, staff["bad"])
    out = admin_client.post("/api/mgmt/close", json=BODY).json()
    assert out["ok"] is True and out["skipped_closed"] == 1
    assert sorted(d["employee_id"] for d in out["done"]) == sorted([staff["ok2"], staff["bad"]])


def test_recalculate_all_or_nothing(admin_client, staff):
    from tests.period_ops import period_action

    for key in ("ok1", "ok2"):
        assert period_action("close", staff[key], PREV.year, PREV.month)["errors"] == []
    out = admin_client.post("/api/mgmt/recalculate", json=BODY).json()
    assert out["ok"] is False and out["done"] == []
    assert [e["employee_id"] for e in out["errors"]] == [staff["bad"]]
    revisions = admin_client.get("/api/mgmt", params={**BODY, "employee_id": staff["ok1"]}).json()
    assert revisions["rows"][0]["revision"] == 1               # пересчёта не было


def test_employee_ids_are_rejected(admin_client):
    for kind in ("close", "recalculate"):
        r = admin_client.post(f"/api/mgmt/{kind}", json={**BODY, "employee_ids": [1]})
        assert r.status_code == 422, r.text


def test_settings_show_who_is_not_closed(admin_client, staff, monkeypatch, db):
    """Индикатор настроек — по сотрудникам: «закрыт у N из M» и кто не закрыт."""
    from app.modules.timesheet.interface import engine_settings_api, mgmt_api
    from tests.period_ops import period_action

    monkeypatch.setattr(engine_settings_api, "period_employees", mgmt_api.period_employees)
    assert period_action("close", staff["ok1"], PREV.year, PREV.month)["errors"] == []
    state = engine_settings_api.period_state_of(db, PREV)
    assert state["closed"] is True and state["complete"] is False
    assert (state["closed_count"], state["total"]) == (1, 3)
    assert state["not_closed"] == ["Порядков Тест Закрытия", "Пропусков Тест Закрытия"]
    assert state["recalc_available"] is False                # пересчёт — только у всех

    _fill(admin_client, staff["bad"])
    assert admin_client.post("/api/mgmt/close", json=BODY).json()["ok"] is True
    db.expire_all()
    state = engine_settings_api.period_state_of(db, PREV)
    assert state["complete"] is True and state["not_closed"] == [] and state["closed_count"] == 3
