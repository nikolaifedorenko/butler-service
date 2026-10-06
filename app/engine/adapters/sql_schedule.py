"""ShiftPort и AbsencePort поверх Графика прототипа (ручные ячейки + базовый цикл блоков)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...base_schedule import BlockIndex, effective_entry_shift, load_base_config
from ...employment import employed_on
from ...models import Employee, EmploymentPeriod, ScheduleEntry
from ...schedule_helpers import authorized_gap, shift_window
from ...shiftrev import ShiftCatalog
from ..domain.types.entities import Absence, Period, Shift
from ._db import days_of, emp_pk, local_naive_to_utc


class ScheduleCache:
    """Предзагрузка Графика один раз на запрос (ячейки, блоки, словарь смен, периоды работы)."""

    def __init__(self, db: Session):
        self.db = db
        self.catalog = ShiftCatalog.load(db)
        self.cfg = load_base_config(db)
        self._index: BlockIndex | None = None
        self._entries: dict = {}
        self._loaded: set = set()
        self._periods: dict[int, list] = {}

    def preload(self, emp_ids: list[int], start: dt.date, end: dt.date) -> None:
        self._index = BlockIndex.load(self.db, emp_ids)
        for e in self.db.scalars(select(ScheduleEntry).where(
                ScheduleEntry.employee_id.in_(emp_ids), ScheduleEntry.date >= start, ScheduleEntry.date <= end)):
            self._entries[(e.employee_id, e.date)] = e
        for p in self.db.scalars(select(EmploymentPeriod).where(EmploymentPeriod.employee_id.in_(emp_ids))):
            self._periods.setdefault(p.employee_id, []).append(p)
        self._loaded |= {(i, start, end) for i in emp_ids}

    def _ensure(self, emp_id: int, start: dt.date, end: dt.date) -> None:
        if not any(i == emp_id and s <= start and end <= e for i, s, e in self._loaded):
            self.preload([emp_id], start, end)

    def day(self, emp: Employee, date: dt.date):
        """(ячейка, эффективная смена) — ручная ячейка важнее базового цикла."""
        self._ensure(emp.id, date, date)
        employed = employed_on(self._periods.get(emp.id, []), date)
        return effective_entry_shift(self.db, emp.id, date, emp=emp, index=self._index, catalog=self.catalog,
                                     entry_map=self._entries, cfg=self.cfg, employed=employed)


class SqlScheduleAdapter:
    def __init__(self, db: Session, cache: ScheduleCache | None = None):
        self.db = db
        self.cache = cache or ScheduleCache(db)

    def _days(self, employee_id: str, period: Period):
        getter = getattr(self, "db_get", None)
        emp = getter(emp_pk(employee_id)) if getter else self.db.get(Employee, emp_pk(employee_id))
        if emp is None:
            return []
        start = period.start - dt.timedelta(days=1)
        self.cache._ensure(emp.id, start, period.end)
        return [(d, *self.cache.day(emp, d)) for d in days_of(start, period.end)]

    def shifts(self, employee_id: str, period: Period) -> list[Shift]:
        out = []
        for d, _entry, shift in self._days(employee_id, period):
            ws, we = shift_window(shift, d)
            if ws and we and we > ws:
                out.append(Shift(employee_id, local_naive_to_utc(ws), local_naive_to_utc(we)))
        return out

    def absences(self, employee_id: str, period: Period) -> list[Absence]:
        out = []
        for d, entry, _shift in self._days(employee_id, period):
            gap = authorized_gap(entry, d)
            if not gap:
                continue
            for day in sorted({gap[0].date(), (gap[1] - dt.timedelta(microseconds=1)).date()}):
                lo = max(gap[0], dt.datetime.combine(day, dt.time(0)))
                hi = min(gap[1], dt.datetime.combine(day, dt.time(0)) + dt.timedelta(days=1))
                a = int((lo - dt.datetime.combine(day, dt.time(0))).total_seconds() // 60)
                b = int((hi - dt.datetime.combine(day, dt.time(0))).total_seconds() // 60)
                if b > a:          # В-Отс1/В-Отс2 — проверки адаптера
                    out.append(Absence(employee_id, day, a, b))
        return out
