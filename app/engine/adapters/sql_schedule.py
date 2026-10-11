"""ShiftPort / AbsencePort / ScheduleStorePort поверх schedule_shifts и schedule_absences.

Контракт выборки (v7.1/F-04): все записи, ПЕРЕСЕКАЮЩИЕ [00:00 period.start,
00:00 period.end+1) в tz объекта, включая начинающиеся до периода; батч-методы —
пересекающие сутки. Валидация уровня 3 при чтении (5.3): CHK-SHIFT-ORDER,
CHK-ABSENCE-ORDER, CHK-ABSENCE-LENGTH → ConfigError до входа в домен.
Моменты хранятся naive UTC; наружу — UTC-aware."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...models import ScheduleAbsence, ScheduleShift
from ..domain.types.entities import Absence, Period, Shift, ShiftEntry
from ..domain.types.errors import ConfigError
from ._db import emp_pk, local_midnight_utc, utc_naive_to_aware

DAY = dt.timedelta(days=1)
MAX_ABSENCE = dt.timedelta(hours=24)


def _validate_shift(row: ScheduleShift) -> None:
    if row.start_utc >= row.end_utc:
        raise ConfigError([("CHK-SHIFT-ORDER",
                            {"id": row.id, "start": str(row.start_utc), "end": str(row.end_utc)})])


def _validate_absence(row: ScheduleAbsence) -> None:
    if row.start_utc >= row.end_utc:
        raise ConfigError([("CHK-ABSENCE-ORDER",
                            {"id": row.id, "start": str(row.start_utc), "end": str(row.end_utc)})])
    if row.end_utc - row.start_utc > MAX_ABSENCE:
        raise ConfigError([("CHK-ABSENCE-LENGTH",
                            {"id": row.id, "start": str(row.start_utc), "end": str(row.end_utc)})])


def _shift(row: ScheduleShift) -> Shift:
    _validate_shift(row)
    return Shift(str(row.employee_id), utc_naive_to_aware(row.start_utc),
                 utc_naive_to_aware(row.end_utc))


def _absence(row: ScheduleAbsence) -> Absence:
    _validate_absence(row)
    return Absence(str(row.employee_id), utc_naive_to_aware(row.start_utc),
                   utc_naive_to_aware(row.end_utc))


class SqlShiftAdapter:
    def __init__(self, db: Session, tz):
        self.db, self.tz = db, tz

    def _window(self, start: dt.date, end_exclusive: dt.date):
        return (local_midnight_utc(start, self.tz).replace(tzinfo=None),
                local_midnight_utc(end_exclusive, self.tz).replace(tzinfo=None))

    def shifts(self, employee_id: str, period: Period) -> list[Shift]:
        lo, hi = self._window(period.start, period.end + DAY)
        rows = self.db.scalars(select(ScheduleShift).where(
            ScheduleShift.employee_id == emp_pk(employee_id),
            ScheduleShift.start_utc < hi, ScheduleShift.end_utc > lo)
            .order_by(ScheduleShift.start_utc, ScheduleShift.id))
        return [_shift(r) for r in rows]

    def shifts_on_day(self, day: dt.date) -> list[Shift]:
        lo, hi = self._window(day, day + DAY)
        rows = self.db.scalars(select(ScheduleShift).where(
            ScheduleShift.start_utc < hi, ScheduleShift.end_utc > lo)
            .order_by(ScheduleShift.start_utc, ScheduleShift.id))
        return [_shift(r) for r in rows]


class SqlAbsenceAdapter:
    def __init__(self, db: Session, tz):
        self.db, self.tz = db, tz

    def _window(self, start: dt.date, end_exclusive: dt.date):
        return (local_midnight_utc(start, self.tz).replace(tzinfo=None),
                local_midnight_utc(end_exclusive, self.tz).replace(tzinfo=None))

    def absences(self, employee_id: str, period: Period) -> list[Absence]:
        lo, hi = self._window(period.start, period.end + DAY)
        rows = self.db.scalars(select(ScheduleAbsence).where(
            ScheduleAbsence.employee_id == emp_pk(employee_id),
            ScheduleAbsence.start_utc < hi, ScheduleAbsence.end_utc > lo)
            .order_by(ScheduleAbsence.start_utc, ScheduleAbsence.id))
        return [_absence(r) for r in rows]

    def absences_on_day(self, day: dt.date) -> list[Absence]:
        lo, hi = self._window(day, day + DAY)
        rows = self.db.scalars(select(ScheduleAbsence).where(
            ScheduleAbsence.start_utc < hi, ScheduleAbsence.end_utc > lo)
            .order_by(ScheduleAbsence.start_utc, ScheduleAbsence.id))
        return [_absence(r) for r in rows]


class SqlScheduleStore:
    """Хранилище Графика вкладки (16.3): generated/manual записи и отсутствия."""

    def __init__(self, db: Session, tz):
        self.db, self.tz = db, tz

    def load_entries(self, employee_id: str | None, period: Period) -> list[ShiftEntry]:
        lo = local_midnight_utc(period.start, self.tz).replace(tzinfo=None)
        hi = local_midnight_utc(period.end + DAY, self.tz).replace(tzinfo=None)
        q = select(ScheduleShift).where(ScheduleShift.start_utc < hi, ScheduleShift.end_utc > lo)
        if employee_id is not None:
            q = q.where(ScheduleShift.employee_id == emp_pk(employee_id))
        rows = self.db.scalars(q.order_by(ScheduleShift.date, ScheduleShift.start_utc,
                                          ScheduleShift.id))
        return [ShiftEntry(_shift(r), r.source) for r in rows]

    def save_manual(self, employee_id: str, day: dt.date, shifts) -> None:
        emp = emp_pk(employee_id)
        self.db.execute(delete(ScheduleShift).where(ScheduleShift.employee_id == emp,
                                                    ScheduleShift.date == day,
                                                    ScheduleShift.source == "manual"))
        for s in shifts:
            if s.start_utc >= s.end_utc:
                raise ConfigError([("CHK-SHIFT-ORDER", {"day": day.isoformat()})])
            self.db.add(ScheduleShift(employee_id=emp, date=day,
                                      start_utc=s.start_utc.astimezone(dt.timezone.utc)
                                      .replace(tzinfo=None),
                                      end_utc=s.end_utc.astimezone(dt.timezone.utc)
                                      .replace(tzinfo=None),
                                      source="manual"))
        self.db.flush()

    def drop_manual(self, employee_id: str, day: dt.date) -> None:
        self.db.execute(delete(ScheduleShift).where(
            ScheduleShift.employee_id == emp_pk(employee_id), ScheduleShift.date == day,
            ScheduleShift.source == "manual"))

    def replace_generated(self, employee_id: str, period: Period, entries) -> None:
        emp = emp_pk(employee_id)
        self.db.execute(delete(ScheduleShift).where(
            ScheduleShift.employee_id == emp, ScheduleShift.source == "generated",
            ScheduleShift.date >= period.start, ScheduleShift.date <= period.end))
        for entry in entries:
            s = entry.shift
            self.db.add(ScheduleShift(employee_id=emp,
                                      date=s.start_utc.astimezone(self.tz).date(),
                                      start_utc=s.start_utc.astimezone(dt.timezone.utc)
                                      .replace(tzinfo=None),
                                      end_utc=s.end_utc.astimezone(dt.timezone.utc)
                                      .replace(tzinfo=None),
                                      source="generated"))
        self.db.flush()

    def save_absence(self, employee_id: str, day: dt.date, start_hhmm: str, end_hhmm: str,
                     end_next_day: bool) -> int:
        """5.1: UI вводит дату и интервал HH:MM–HH:MM (в т.ч. с переходом на следующие
        сутки); адаптер конвертирует в UTC-интервал и валидирует (уровень 3)."""
        start_local = _at_local(day, start_hhmm, self.tz)
        end_local = _at_local(day + (DAY if end_next_day else dt.timedelta()), end_hhmm, self.tz)
        if start_local >= end_local:
            raise ConfigError([("CHK-ABSENCE-ORDER",
                                {"day": day.isoformat(), "start": start_hhmm, "end": end_hhmm})])
        if end_local - start_local > MAX_ABSENCE:
            raise ConfigError([("CHK-ABSENCE-LENGTH",
                                {"day": day.isoformat(), "start": start_hhmm, "end": end_hhmm})])
        row = ScheduleAbsence(employee_id=emp_pk(employee_id),
                              start_utc=start_local.astimezone(dt.timezone.utc).replace(tzinfo=None),
                              end_utc=end_local.astimezone(dt.timezone.utc).replace(tzinfo=None))
        self.db.add(row)
        self.db.flush()
        return row.id

    def drop_absence(self, absence_id: int) -> None:
        row = self.db.get(ScheduleAbsence, absence_id)
        if row is not None:
            self.db.delete(row)


def _at_local(day: dt.date, hhmm: str, tz) -> dt.datetime:
    hh, mm = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(hh, mm), tz)
