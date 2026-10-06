"""BankPort: входящий банк = закрывающий банк предыдущего закрытого периода, иначе стартовый
банк сотрудника; корректировки — BankAdjustment с датой действия внутри периода."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import BankAdjustment, Employee, PeriodClosing
from ..domain.types.entities import Adjustment, Period
from ._db import emp_pk


def _minutes(hours: float) -> int:
    return int(round((hours or 0.0) * 60))


class SqlBankAdapter:
    def __init__(self, db: Session):
        self.db = db

    def _last_closing(self, emp: int, before: dt.date) -> PeriodClosing | None:
        return self.db.scalar(select(PeriodClosing).where(
            PeriodClosing.employee_id == emp, PeriodClosing.period_end < before)
            .order_by(PeriodClosing.period_end.desc()).limit(1))

    def _adjust_sum(self, emp: int, lo: dt.date | None, hi: dt.date) -> int:
        q = select(func.coalesce(func.sum(BankAdjustment.hours), 0.0)).where(
            BankAdjustment.employee_id == emp, BankAdjustment.effective_date < hi)
        if lo is not None:
            q = q.where(BankAdjustment.effective_date > lo)
        return _minutes(self.db.scalar(q))

    def opening(self, employee_id: str, period: Period) -> int:
        emp = emp_pk(employee_id)
        last = self._last_closing(emp, period.start)
        if last is not None:   # корректировки «в разрыве» незакрытых месяцев не теряются
            return last.closing_bank_minutes + self._adjust_sum(emp, last.period_end, period.start)
        e = self.db.get(Employee, emp)
        return _minutes(e.balance_hours if e else 0.0) + self._adjust_sum(emp, None, period.start)

    def adjustments(self, employee_id: str, period: Period) -> list[Adjustment]:
        rows = self.db.scalars(select(BankAdjustment).where(
            BankAdjustment.employee_id == emp_pk(employee_id), BankAdjustment.effective_date >= period.start,
            BankAdjustment.effective_date <= period.end).order_by(BankAdjustment.id))
        return [Adjustment(_minutes(r.hours), "manual", r.note or None) for r in rows]
