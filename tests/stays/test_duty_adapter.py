"""Шахматка, задача 12: DutyPort поверх Графика."""
from __future__ import annotations

import datetime as dt

from app.modules.stays.adapters.duty_timesheet import TimesheetDuty
from app.modules.stays.ports.duty import OFF, DutyDay
from tests.test_roster import D0, _clean, _staff, _utc


def test_duty_maps_roster(db):
    from app.modules.timesheet.application.catalog import ScheduleAbsence, ScheduleShift, TabelDay
    a, b = _staff(db, 2)
    _clean(db, [a, b])
    db.add_all([ScheduleShift(employee_id=a, date=D0, start_utc=_utc(D0, 8), end_utc=_utc(D0, 20), source="manual"),
                ScheduleAbsence(employee_id=a, start_utc=_utc(D0, 10), end_utc=_utc(D0, 11)),
                TabelDay(employee_id=b, date=D0, code="Б", plan_minutes=0)])
    db.commit()
    got = TimesheetDuty(db).duty([a, b], D0, D0 + dt.timedelta(days=1))
    assert got[(a, D0)] == DutyDay(True, None, True)
    assert got[(b, D0)] == DutyDay(False, "Б", False)
    assert got.get((a, D0 + dt.timedelta(days=1)), OFF) == OFF
    _clean(db, [a, b])


def test_preset_shifts(db):
    from app.modules.timesheet.application.catalog import ShiftType
    from app.modules.timesheet.application.schedule_view import preset_shifts
    kind = ShiftType(name="ночь", kind="work", start_time="20:00", end_time="08:00", overnight=True)
    (s,) = preset_shifts("7", D0, kind)
    assert s.employee_id == "7"
    assert s.start_utc.replace(tzinfo=None) == _utc(D0, 20) and s.end_utc.replace(tzinfo=None) == _utc(D0 + dt.timedelta(days=1), 8)
