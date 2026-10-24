"""SettlementStorePort / BankWritePort / CarryOverPort поверх period_closings и
deferred_carry (7.3). PeriodState — closed/previous_closed/next_closed/opening_bank_set
(v7/R26, R37); цепочка периодов — по гранулярности настройки (R36). Сохранение —
в одной транзакции UnitOfWork; уникальный ключ (сотрудник, период) запрещает
конкурентное повторное закрытие."""
from __future__ import annotations

import datetime as dt
import json
from typing import Sequence

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import lock_employee
from app.core.time import utcnow

from ..domain.types.entities import ClosingInputs, DeferredBlock, Period, PeriodState
from ..domain.types.results import FlagsResult, SettleResult
from ..interface.deserialize import flags_from_dict, result_from_dict
from ..interface.serialize import flags_to_dict, result_to_dict
from ..ports.unit_of_work import StorageConflictError
from ._db import emp_pk
from .orm import DeferredCarry, PeriodClosing
from .sql_bank import opening_seed_set, previous_closing


def _block_dict(b: DeferredBlock) -> dict:
    return {"source_day": b.source_day.isoformat(), "tariff": b.tariff, "minutes": b.minutes}


def _block(d: dict) -> DeferredBlock:
    return DeferredBlock(dt.date.fromisoformat(d["source_day"]), d["tariff"], int(d["minutes"]))


class SqlSettlementStore:
    def __init__(self, db: Session, settings_port, actor_name: str = ""):
        self.db, self.settings, self.actor = db, settings_port, actor_name

    def _row(self, employee_id: str, period: Period) -> PeriodClosing | None:
        return self.db.scalar(select(PeriodClosing).where(
            PeriodClosing.employee_id == emp_pk(employee_id),
            PeriodClosing.period_start == period.start))

    def period_state(self, employee_id: str, period: Period) -> PeriodState:
        """Цепочка периодов (R36): previous — закрытие, смежное слева (как opening банка:
        на смене гранулярности начало «предыдущего периода» указало бы не на ту строку);
        next — любое сохранённое закрытие, начинающееся после period.end (7.2: пересчёт
        запрещён, если следующий уже закрыт)."""
        emp = emp_pk(employee_id)
        first = not self.db.scalar(select(PeriodClosing.id).where(
            PeriodClosing.employee_id == emp, PeriodClosing.period_start < period.start).limit(1))
        later = self.db.scalar(select(PeriodClosing.id).where(
            PeriodClosing.employee_id == emp, PeriodClosing.period_start > period.end).limit(1))
        return PeriodState(
            closed=self._row(employee_id, period) is not None,
            previous_closed=previous_closing(self.db, emp, period) is not None,
            next_closed=later is not None,
            opening_bank_set=first and opening_seed_set(self.db, employee_id, period))

    def lock_marks(self, employee_ids: Sequence[str],
                   period: Period) -> dict[str, tuple[bool, bool]]:
        """closed и next_closed как в period_state, но одним запросом на всех."""
        pks = {emp_pk(e): e for e in employee_ids}
        marks = {e: (False, False) for e in employee_ids}
        for emp, start in self.db.execute(select(PeriodClosing.employee_id, PeriodClosing.period_start)
                                          .where(PeriodClosing.employee_id.in_(pks),
                                                 or_(PeriodClosing.period_start == period.start,
                                                     PeriodClosing.period_start > period.end))):
            closed, later = marks[pks[emp]]
            marks[pks[emp]] = (closed or start == period.start, later or start > period.end)
        return marks

    def lock_employee(self, employee_id: str) -> None:
        lock_employee(self.db, emp_pk(employee_id))

    def closing_inputs(self, employee_id: str, period: Period) -> ClosingInputs | None:
        row = self._row(employee_id, period)
        if row is None:
            return None
        blocks = tuple(_block(d) for d in json.loads(row.deferred_in_json or "[]"))
        return ClosingInputs(row.bank_open_minutes, blocks, row.previous_step_minutes)

    def save_result(self, employee_id: str, period: Period, result: SettleResult,
                    flags: FlagsResult, inputs_snapshot: ClosingInputs,
                    settings_versions: Sequence[str], step_minutes: int) -> None:
        row = self._row(employee_id, period)
        if row is None:
            row = PeriodClosing(employee_id=emp_pk(employee_id), period_start=period.start,
                                revision=0)
            self.db.add(row)
        row.period_end = period.end
        row.step_minutes = step_minutes
        row.previous_step_minutes = inputs_snapshot.previous_step_minutes
        row.bank_open_minutes = inputs_snapshot.bank_open
        row.deferred_in_json = json.dumps([_block_dict(b) for b in inputs_snapshot.deferred_in])
        row.settings_versions = ",".join(settings_versions)
        row.result_json = json.dumps(result_to_dict(result), ensure_ascii=False)
        row.flags_json = json.dumps(flags_to_dict(flags), ensure_ascii=False)
        row.closing_bank_minutes = result.bank_closed_minutes
        row.revision = (row.revision or 0) + 1
        row.closed_by_name, row.closed_at = self.actor, utcnow()
        try:
            self.db.flush()   # уникальный ключ (сотрудник, период) исключает конкурентное закрытие
        except IntegrityError as exc:
            # конкурентное закрытие (7.3): проверка права прошла до коммита соперника,
            # гонку закрыл уникальный ключ — контрактный сигнал порта, use case
            # переведёт его в PeriodAlreadyClosedError (409, P1-ts-1). Откатывает UoW.
            raise StorageConflictError(str(getattr(exc, "orig", exc))) from exc

    def load_result(self, employee_id: str, period: Period) -> tuple[SettleResult, FlagsResult] | None:
        row = self._row(employee_id, period)
        if row is None:
            return None
        flags = flags_from_dict(json.loads(row.flags_json)) if row.flags_json else FlagsResult(())
        return result_from_dict(json.loads(row.result_json)), flags

    def saved_meta(self, employee_id: str, period: Period) -> dict | None:
        row = self._row(employee_id, period)
        if row is None:
            return None
        return {"revision": row.revision, "closed_by": row.closed_by_name,
                "closed_at": row.closed_at.isoformat() if row.closed_at else None,
                "versions": (row.settings_versions or "").split(",") if row.settings_versions else []}


class SqlBankWrite:
    def __init__(self, db: Session):
        self.db = db

    def save_closing_bank(self, employee_id: str, period: Period, closing_minutes: int) -> None:
        row = self.db.scalar(select(PeriodClosing).where(
            PeriodClosing.employee_id == emp_pk(employee_id),
            PeriodClosing.period_start == period.start))
        if row is not None:
            row.closing_bank_minutes = closing_minutes
            self.db.flush()


class SqlCarryOver:
    def __init__(self, db: Session):
        self.db = db

    def load_deferred(self, employee_id: str, period: Period) -> list[DeferredBlock]:
        rows = self.db.scalars(select(DeferredCarry).where(
            DeferredCarry.employee_id == emp_pk(employee_id),
            DeferredCarry.period_start == period.start).order_by(DeferredCarry.id))
        return [DeferredBlock(r.source_day, r.tariff, r.minutes) for r in rows]

    def save_deferred(self, employee_id: str, next_period_: Period,
                      blocks: Sequence[DeferredBlock]) -> None:
        """ЗАМЕНА входа следующего периода (7.2): исчезнувшие переносы удаляются."""
        emp = emp_pk(employee_id)
        self.db.execute(delete(DeferredCarry).where(DeferredCarry.employee_id == emp,
                                                    DeferredCarry.period_start == next_period_.start))
        for b in blocks:
            self.db.add(DeferredCarry(employee_id=emp, period_start=next_period_.start,
                                      source_day=b.source_day, tariff=b.tariff, minutes=b.minutes))
        self.db.flush()
