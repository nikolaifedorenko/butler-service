"""TimesheetPort поверх таблицы tabel_days (Табель — независим от Графика)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...employment import employed_on
from ...groups import GROUP_OTHER, normalize_group
from ...models import Employee, EmploymentPeriod, TabelDay
from ..domain.types.entities import Day, Period
from ._db import days_of, emp_pk

# день без строки Табеля внутри периода работы: выходной без часов (работа = переработка)
EMPTY_DAY_CODE = "В"


def employee_group(emp: Employee, known: set[str]) -> str:
    """Ровно одна группа сотрудника (В-Гр1/В-Гр2): блок графика; неизвестный → «Другие смены»."""
    g = normalize_group(emp.schedule_group)
    return g if g in known else GROUP_OTHER


class SqlTimesheetAdapter:
    def __init__(self, db: Session, settings_port):
        self.db, self.settings = db, settings_port

    def days(self, employee_id: str, period: Period) -> list[Day]:
        emp = self.db.get(Employee, emp_pk(employee_id))
        if emp is None:
            return []
        rows = {r.date: r for r in self.db.scalars(select(TabelDay).where(
            TabelDay.employee_id == emp.id, TabelDay.date >= period.start, TabelDay.date <= period.end))}
        periods = list(self.db.scalars(select(EmploymentPeriod).where(EmploymentPeriod.employee_id == emp.id)))
        group = employee_group(emp, set(self.settings.load(period).groups))
        employed = [d for d in days_of(period.start, period.end) if not periods or employed_on(periods, d)]
        return [Day(d, rows[d].code if d in rows else EMPTY_DAY_CODE, rows[d].plan_minutes if d in rows else 0,
                    employee_id, group) for d in employed]


def tabel_rows(db: Session, emp_ids: list[int], first: dt.date, last: dt.date) -> dict:
    return {(r.employee_id, r.date): r for r in db.scalars(select(TabelDay).where(
        TabelDay.employee_id.in_(emp_ids), TabelDay.date >= first, TabelDay.date <= last))} if emp_ids else {}
