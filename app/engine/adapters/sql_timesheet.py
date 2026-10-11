"""TimesheetPort поверх tabel_days: строки Табеля КАК ЕСТЬ за полный запрошенный период
(v7/R27 — строки вне трудоустройства отбраковывает домен, CHK-DAYS-IN-PERIOD); пропуски
не заполняются (RUL-TIMESHEET-COVERS-PERIOD проверяет расчёт). Группа — из истории
блоков сотрудника на соответствующий день (RUL-GROUP-PER-DAY)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...base_schedule import BlockIndex, group_for_date
from ...groups import GROUP_OTHER, normalize_group
from ...models import BlockAssignment, Employee, TabelDay
from ..domain.types.entities import Day, Period
from ._db import emp_pk


class SqlTimesheetAdapter:
    def __init__(self, db: Session, groups_known: set[str] | None = None):
        self.db = db
        self._groups = groups_known
        self._group_cache: dict[tuple[int, dt.date], str] = {}
        self._indexes: dict[int, BlockIndex] = {}

    def _index(self, emp_id: int) -> BlockIndex:
        if emp_id not in self._indexes:
            rows = list(self.db.scalars(select(BlockAssignment).where(
                BlockAssignment.employee_id == emp_id).order_by(BlockAssignment.start_date)))
            self._indexes[emp_id] = BlockIndex.from_assignments(rows)
        return self._indexes[emp_id]

    def _group(self, emp: Employee, day: dt.date) -> str:
        key = (emp.id, day)
        if key not in self._group_cache:
            group = normalize_group(group_for_date(self.db, emp, day,
                                                   index=self._index(emp.id))
                                    or emp.schedule_group)
            known = self._groups
            self._group_cache[key] = group if known is None or group in known else GROUP_OTHER
        return self._group_cache[key]

    def days(self, employee_id: str, period: Period) -> list[Day]:
        emp = self.db.get(Employee, emp_pk(employee_id))
        if emp is None:
            return []
        rows = self.db.scalars(select(TabelDay).where(
            TabelDay.employee_id == emp.id, TabelDay.date >= period.start,
            TabelDay.date <= period.end).order_by(TabelDay.date))
        return [Day(r.date, r.code, r.plan_minutes, employee_id, self._group(emp, r.date))
                for r in rows]


def tabel_rows(db: Session, emp_ids: list[int], first: dt.date, last: dt.date) -> dict:
    return {(r.employee_id, r.date): r for r in db.scalars(select(TabelDay).where(
        TabelDay.employee_id.in_(emp_ids), TabelDay.date >= first,
        TabelDay.date <= last))} if emp_ids else {}


