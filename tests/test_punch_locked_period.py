"""Отметки и «замороженный» период (аудит 22.10.2026): период, за которым уже закрыт следующий,
пересчитать нельзя — значит, его исходные данные не меняются. Табель это соблюдал, а отметка
задним числом и отмена отметки проходили: Факт расходился с закрытым УТ. Последний закрытый
период править можно (его пересчитывают), как и Табель.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.core.time import local_date


def _month_start(d: dt.date, back: int) -> dt.date:
    y, m = d.year, d.month - back
    while m < 1:
        y, m = y - 1, m + 12
    return dt.date(y, m, 1)


@pytest.fixture()
def closed_two_months(db):
    """У сотрудника закрыты два прошлых месяца: позапрошлый — «заморожен», прошлый — последний."""
    from app.modules.employees.application.catalog import Employee
    from app.modules.timesheet.adapters.orm import PeriodClosing, Punch

    emp = db.scalar(select(Employee).where(Employee.full_name.like("Иванов%")))
    m2, m1, m0 = (_month_start(local_date(), k) for k in (2, 1, 0))
    # другие тесты набора могли уже закрыть эти месяцы — добавляем только недостающие закрытия
    have = set(db.scalars(select(PeriodClosing.period_start).where(PeriodClosing.employee_id == emp.id)))
    rows = [PeriodClosing(employee_id=emp.id, period_start=s, period_end=e)
            for s, e in ((m2, m1 - dt.timedelta(days=1)), (m1, m0 - dt.timedelta(days=1)))
            if s not in have]
    assert not db.scalar(select(PeriodClosing.id).where(PeriodClosing.employee_id == emp.id,
                                                        PeriodClosing.period_start >= m0)), \
        "текущий месяц закрыт — прошлый уже не «последний закрытый», тест не о том"
    old = Punch(employee_id=emp.id, ts=dt.datetime.combine(m1 - dt.timedelta(days=1), dt.time(8)),
                kind="IN", source="manual")
    db.add_all([*rows, old])
    db.commit()
    yield emp, m1 - dt.timedelta(days=1), m0 - dt.timedelta(days=1), old.id
    db.query(Punch).filter(Punch.employee_id == emp.id, Punch.note == "проба периода").delete()
    for r in [*rows, db.get(Punch, old.id)]:
        if r is not None:
            db.delete(r)
    db.commit()


def test_frozen_period_rejects_backfill_and_cancel(manager_client, closed_two_months):
    emp, frozen_day, _last_closed_day, old_id = closed_two_months
    r = manager_client.post("/api/punches", json={
        "employee_id": emp.id, "kind": "out", "ts": f"{frozen_day}T20:00", "note": "проба периода"})
    assert r.status_code == 409, r.text
    assert "следующий уже закрыт" in r.json()["detail"]
    r = manager_client.delete(f"/api/punches/{old_id}")
    assert r.status_code == 409, r.text


def test_last_closed_period_still_accepts_backfill(manager_client, closed_two_months):
    emp, _frozen_day, last_closed_day, _old_id = closed_two_months
    r = manager_client.post("/api/punches", json={
        "employee_id": emp.id, "kind": "out", "ts": f"{last_closed_day}T20:00", "note": "проба периода"})
    assert r.status_code == 200, r.text
    # как правка Табеля: в закрытый результат отметка попадёт только через пересчёт
    assert any("пересчёт" in w for w in r.json()["warnings"]), r.json()["warnings"]


def test_cancel_in_last_closed_period_warns_about_recalculation(manager_client, closed_two_months, db):
    """Отмена отметки из последнего закрытого периода: раньше — молчаливое {"ok": true},
    хотя закрытый результат её ещё учитывает (рецензия аудита 22.10.2026, P1)."""
    from app.modules.timesheet.adapters.orm import Punch

    emp, _frozen_day, last_closed_day, _old_id = closed_two_months
    p = Punch(employee_id=emp.id, ts=dt.datetime.combine(last_closed_day, dt.time(21)),
              kind="OUT", source="manual", note="проба периода")
    db.add(p)
    db.commit()
    r = manager_client.delete(f"/api/punches/{p.id}")
    assert r.status_code == 200, r.text
    assert "пересчёт" in (r.json().get("warning") or ""), r.text


def test_cancel_in_open_period_has_no_warning(manager_client, db):
    from app.modules.employees.application.catalog import Employee
    from app.modules.timesheet.adapters.orm import Punch

    emp = db.scalar(select(Employee).where(Employee.full_name.like("Иванов%")))
    p = Punch(employee_id=emp.id, ts=dt.datetime.combine(local_date(), dt.time(0, 1)),
              kind="IN", source="manual", note="проба периода")
    db.add(p)
    db.commit()
    r = manager_client.delete(f"/api/punches/{p.id}")
    assert r.status_code == 200 and r.json().get("warning") is None, r.text


def test_month_journal_is_not_truncated(manager_client, db):
    """Журнал за месяц отдаёт все отметки: раньше выдача обрезалась на 2000 строках, и при
    ~35 сотрудниках начало месяца пропадало молча (аудит 22.10.2026)."""
    from app.modules.employees.application.catalog import Employee
    from app.modules.timesheet.adapters.orm import Punch

    emp = db.scalar(select(Employee).where(Employee.full_name.like("Иванов%")))
    base = dt.datetime(2031, 1, 1, 6, 0)
    rows = [Punch(employee_id=emp.id, ts=base + dt.timedelta(minutes=20 * i),
                  kind="IN" if i % 2 == 0 else "OUT", source="manual", note="проба журнала")
            for i in range(2050)]
    db.add_all(rows)
    db.commit()
    try:
        r = manager_client.get("/api/punches", params={"year": 2031, "month": 1})
        assert r.status_code == 200
        assert len(r.json()) == 2050
    finally:
        db.query(Punch).filter(Punch.note == "проба журнала").delete()
        db.commit()
