"""EmploymentPort поверх employment_periods (v7/R23, v7.1/R38).

employment() возвращает интервал трудоустройства, пересекающий запрошенный период;
если пересечения нет — интервал, дающий пустое пересечение (application отклоняет
период типизированной ошибкой, R35). active_employees(on_day) — батч одним запросом
популяции доски: трудоустроенные на день (уволенные с незакрытой сессией не попадают)."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.employees.application import Employee, EmploymentPeriod, ensure_periods

from ..domain.types.entities import Employment, Period
from ._db import emp_pk


class SqlEmploymentAdapter:
    def __init__(self, db: Session):
        self.db = db
        self._pre: dict[int, list[EmploymentPeriod]] = {}

    def prefetch(self, employee_ids: Sequence[str]) -> None:
        """Периоды трудоустройства многих сотрудников одним запросом (PERF-02)."""
        pks = [emp_pk(e) for e in employee_ids]
        self._pre = {pk: [] for pk in pks}
        for r in self.db.scalars(select(EmploymentPeriod).where(
                EmploymentPeriod.employee_id.in_(pks)).order_by(EmploymentPeriod.start_date)):
            self._pre[r.employee_id].append(r)

    def _rows(self, emp: int) -> list[EmploymentPeriod]:
        rows = self._pre.get(emp) or list(self.db.scalars(select(EmploymentPeriod).where(
            EmploymentPeriod.employee_id == emp).order_by(EmploymentPeriod.start_date)))
        if rows:
            return rows
        employee = self.db.get(Employee, emp)
        if employee is None:
            return []
        return ensure_periods(self.db, employee)

    def employment(self, employee_id: str, period: Period) -> Employment:
        emp = emp_pk(employee_id)
        rows = self._rows(emp)
        if not rows:
            employee = self.db.get(Employee, emp)
            if employee is not None and employee.active and employee.deleted_at is None:
                return Employment(dt.date(1900, 1, 1), None)      # бессрочно трудоустроен
            return Employment(period.end + dt.timedelta(days=1), None)  # ∅-пересечение (R35)
        covering = [r for r in rows if r.start_date <= period.end
                    and (r.end_date is None or r.end_date >= period.start)]
        if not covering:
            last = rows[-1]
            return Employment(last.start_date, last.end_date)      # ∅-пересечение (R35)
        row = next((r for r in covering
                    if r.start_date <= period.start
                    and (r.end_date is None or r.end_date >= period.start)), covering[0])
        return Employment(row.start_date, row.end_date)

    def active_employees(self, on_day: dt.date) -> list[str]:
        q = select(Employee.id).where(Employee.deleted_at.is_(None),
                                      or_(Employee.active.is_(True),
                                          Employee.dismissed_at.is_(None)))
        emp_ids = {int(i) for i in self.db.scalars(q)}
        rows = self.db.execute(select(EmploymentPeriod.employee_id, EmploymentPeriod.start_date,
                                       EmploymentPeriod.end_date).where(
                                           EmploymentPeriod.employee_id.in_(emp_ids))).all()
        by_emp: dict[int, list] = {}
        for emp_id, start, end in rows:
            by_emp.setdefault(int(emp_id), []).append((start, end))
        out = []
        for emp_id in emp_ids:
            recs = by_emp.get(emp_id)
            if recs is None:
                out.append(str(emp_id))          # нет записей — считается трудоустроенным
                continue
            if any(s <= on_day and (e is None or e >= on_day) for s, e in recs):
                out.append(str(emp_id))
        return sorted(out, key=int)
