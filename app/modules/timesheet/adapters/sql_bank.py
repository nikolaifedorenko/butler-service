"""BankPort (2.6, v7.1/R37): opening(P) = закрывающий банк предыдущего периода цепочки
(RUL-BANK-CONTINUITY); для первого периода — 0, начальное значение задаётся посевающей
корректировкой OPENING_SEED (конвенция адаптера — ядро маркер не интерпретирует).
adjustments(P) — только корректировки своего периода (Adjustment.period = P)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..application.months import previous_period
from ..domain.types.entities import Adjustment, Period
from ._db import emp_pk
from .orm import BankAdjustment, PeriodClosing

OPENING_SEED = "OPENING_SEED"          # маркер посева (v7.1/R37); ядро его не видит


def _minutes(hours: float) -> int:
    return int(round((hours or 0.0) * 60))


class SqlBankAdapter:
    def __init__(self, db: Session, settings_port):
        self.db, self.settings = db, settings_port

    def _previous_closing(self, emp: int, period: Period) -> PeriodClosing | None:
        granularity = self.settings.load(period).period_granularity
        prev = previous_period(period, granularity)
        return self.db.scalar(select(PeriodClosing).where(
            PeriodClosing.employee_id == emp, PeriodClosing.period_start == prev.start))

    def opening(self, employee_id: str, period: Period) -> int:
        row = self._previous_closing(emp_pk(employee_id), period)
        return row.closing_bank_minutes if row is not None else 0

    def adjustments(self, employee_id: str, period: Period) -> list[Adjustment]:
        rows = self.db.scalars(select(BankAdjustment).where(
            BankAdjustment.employee_id == emp_pk(employee_id),
            BankAdjustment.effective_date >= period.start,
            BankAdjustment.effective_date <= period.end).order_by(BankAdjustment.id))
        return [Adjustment(_minutes(r.hours), period, r.reason_code or "manual", r.note or None)
                for r in rows]


def opening_seed_set(db: Session, employee_id: str, period: Period) -> bool:
    """Признак PeriodState.opening_bank_set: для периода внесена посевающая корректировка
    (в том числе на нулевую сумму — «задано ≠ ноль по умолчанию», R26/R37)."""
    row = db.scalar(select(BankAdjustment.id).where(
        BankAdjustment.employee_id == emp_pk(employee_id),
        BankAdjustment.reason_code == OPENING_SEED,
        BankAdjustment.effective_date >= period.start,
        BankAdjustment.effective_date <= period.end).limit(1))
    return row is not None
