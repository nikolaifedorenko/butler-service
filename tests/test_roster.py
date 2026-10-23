"""Публичный запрос Графика «смены и отсутствия сотрудников на даты» (шахматка, задача 12):
одним пакетом на диапазон — число запросов не зависит от сотрудников и дней."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, select

from app.core.time import TZ
from app.modules.timesheet.application.catalog import ScheduleAbsence, ScheduleShift, TabelDay
from app.modules.timesheet.application.engine_common import engine_ports
from app.modules.timesheet.application.roster import RosterDay, roster

D0 = dt.date(2033, 3, 1)


def _utc(day: dt.date, hh: int, mm: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hh, mm), TZ).astimezone(dt.timezone.utc).replace(tzinfo=None)


def _staff(db, n=3):
    from app.modules.employees.application.catalog import Employee
    return [e.id for e in db.scalars(select(Employee).where(Employee.active.is_(True)).order_by(Employee.id).limit(n))]


def _clean(db, ids):
    db.execute(delete(ScheduleShift).where(ScheduleShift.employee_id.in_(ids), ScheduleShift.date >= D0))
    db.execute(delete(TabelDay).where(TabelDay.employee_id.in_(ids), TabelDay.date >= D0))
    db.execute(delete(ScheduleAbsence).where(ScheduleAbsence.employee_id.in_(ids),
                                             ScheduleAbsence.start_utc >= _utc(D0, 0)))
    db.commit()


def test_roster_day_status(db):
    a, b, c = _staff(db)
    _clean(db, [a, b, c])
    day2 = D0 + dt.timedelta(days=1)
    db.add_all([
        ScheduleShift(employee_id=a, date=D0, start_utc=_utc(D0, 8), end_utc=_utc(D0, 20), source="manual"),
        # ночная 20:00–08:00: смена дня начала, не следующего
        ScheduleShift(employee_id=b, date=D0, start_utc=_utc(D0, 20), end_utc=_utc(day2, 8), source="manual"),
        ScheduleAbsence(employee_id=a, start_utc=_utc(D0, 12), end_utc=_utc(D0, 14)),
        TabelDay(employee_id=c, date=D0, code="ОТ", plan_minutes=0),
    ])
    db.commit()
    got = roster([a, b, c], D0, day2, engine_ports(db))
    assert got[(a, D0)] == RosterDay(True, None, 120)
    assert got[(b, D0)] == RosterDay(True, None, 0)
    assert (b, day2) not in got or got[(b, day2)].on_shift is False
    assert got[(c, D0)] == RosterDay(False, "ОТ", 0)
    assert (a, day2) not in got
    _clean(db, [a, b, c])


def test_roster_three_queries(db, sql_counter):
    ids = _staff(db, 10)
    ports = engine_ports(db)
    with sql_counter() as c:
        roster(ids, D0, D0 + dt.timedelta(days=30), ports)
    assert c["total"] <= 3, c["by_statement"]


def test_roster_empty_staff(db, sql_counter):
    with sql_counter() as c:
        assert roster([], D0, D0, engine_ports(db)) == {}
    assert c["total"] == 0
