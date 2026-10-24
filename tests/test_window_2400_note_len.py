"""Две дешёвые 500-е из рецензии аудита (22.10.2026, топ-4).

Что проверяется:
  * окно, кончающееся в полночь (end_minute = 1440, CHK-WINDOW-BOUNDS это допускает),
    в «Назначить отсутствие» превращается в «00:00 следующих суток», а не в «24:00»,
    на котором dt.time(24, 0) падал ValueError'ом → 500;
  * примечание к отметке обрезается по длине колонки (255), а не по 500 — на
    PostgreSQL 256–500 символов давали 500.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import pytest
from sqlalchemy import delete, select

from app.core.time import TZ
from app.modules.employees.application import Employee
from app.modules.timesheet.adapters.orm import Punch, ScheduleAbsence, TabelDay
from app.modules.timesheet.adapters.sql_schedule import SqlScheduleStore
from app.modules.timesheet.domain.settings.defaults import default_settings
from app.modules.timesheet.domain.settings.types import Window
from app.modules.timesheet.interface.schedule import _day_window_hhmm

DAY = dt.date(2029, 3, 5)


@pytest.fixture
def emp(db):
    return next(e for e in db.scalars(select(Employee)) if "Иванов" in e.display_name)


def test_window_until_midnight_is_next_day_0000(db, emp):
    st = default_settings()
    st = dataclasses.replace(st, windows={**st.windows, "Я 4": Window(1200, 1440)})
    db.add(TabelDay(employee_id=emp.id, date=DAY, code="Я", plan_minutes=240, source="manual"))
    db.flush()
    try:
        assert _day_window_hhmm(db, st, emp.id, DAY) == ("20:00", "00:00", True)
        absence_id = SqlScheduleStore(db, TZ).save_absence(str(emp.id), DAY, "20:00", "00:00", True)
        row = db.get(ScheduleAbsence, absence_id)
        assert row.end_utc - row.start_utc == dt.timedelta(hours=4)
    finally:
        db.rollback()
        db.execute(delete(TabelDay).where(TabelDay.employee_id == emp.id, TabelDay.date == DAY))
        db.commit()


def test_punch_note_fits_column(manager_client, db, emp):
    limit = Punch.__table__.c.note.type.length
    p = Punch(employee_id=emp.id, ts=dt.datetime(2029, 3, 6, 9, 0), kind="IN", source="manual")
    db.add(p)
    db.commit()
    try:
        r = manager_client.put(f"/api/punches/{p.id}/note", json={"note": "я" * 400})
        assert r.status_code == 200, r.text
        assert len(r.json()["note"]) == limit
    finally:
        db.rollback()
        db.execute(delete(Punch).where(Punch.id == p.id))
        db.commit()
