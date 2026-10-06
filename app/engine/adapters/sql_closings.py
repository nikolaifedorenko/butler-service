"""SettlementStorePort, BankWritePort и CarryOverPort поверх period_closings / deferred_carry."""
from __future__ import annotations

import datetime as dt
import json
from typing import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...models import DeferredCarry, PeriodClosing, utcnow
from ..domain.types.entities import DeferredBlock, Period
from ..domain.types.results import SettleResult
from ..interface.serialize import result_to_dict
from ..ports.settlement_store import ClosingInputs, PeriodState
from ._db import emp_pk


def _block_dict(b: DeferredBlock) -> dict:
    return {"source_day": b.source_day.isoformat(), "tariff": b.tariff, "minutes": b.minutes,
            "reason_code": b.reason_code}


def _block(d: dict) -> DeferredBlock:
    return DeferredBlock(dt.date.fromisoformat(d["source_day"]), d["tariff"], int(d["minutes"]), d["reason_code"])


class SqlSettlementStore:
    def __init__(self, db: Session, actor_name: str = ""):
        self.db, self.actor = db, actor_name

    def _row(self, employee_id: str, period: Period) -> PeriodClosing | None:
        return self.db.scalar(select(PeriodClosing).where(PeriodClosing.employee_id == emp_pk(employee_id),
                                                          PeriodClosing.period_start == period.start))

    def period_state(self, employee_id: str, period: Period) -> PeriodState:
        later = self.db.scalar(select(PeriodClosing.id).where(PeriodClosing.employee_id == emp_pk(employee_id),
                                                              PeriodClosing.period_start > period.end).limit(1))
        return PeriodState(self._row(employee_id, period) is not None, later is not None)

    def closing_inputs(self, employee_id: str, period: Period) -> ClosingInputs | None:
        row = self._row(employee_id, period)
        if row is None:
            return None
        blocks = tuple(_block(d) for d in json.loads(row.deferred_in_json or "[]"))
        return ClosingInputs(row.bank_open_minutes, blocks, row.previous_step_minutes)

    def previous_step(self, employee_id: str, period: Period) -> int | None:
        row = self.db.scalar(select(PeriodClosing).where(PeriodClosing.employee_id == emp_pk(employee_id),
                                                         PeriodClosing.period_end < period.start)
                             .order_by(PeriodClosing.period_end.desc()).limit(1))
        return row.step_minutes if row else None

    def save_result(self, employee_id: str, period: Period, result: SettleResult, inputs_snapshot: ClosingInputs,
                    settings_versions: Sequence[str], step_minutes: int, replace: bool) -> None:
        row = self._row(employee_id, period)
        if row is None:
            row = PeriodClosing(employee_id=emp_pk(employee_id), period_start=period.start, revision=0)
            self.db.add(row)
        row.period_end = period.end
        row.step_minutes = step_minutes
        row.previous_step_minutes = inputs_snapshot.previous_step_minutes
        row.bank_open_minutes = inputs_snapshot.bank_open_minutes
        row.deferred_in_json = json.dumps([_block_dict(b) for b in inputs_snapshot.deferred_in])
        row.settings_versions = ",".join(settings_versions)
        row.result_json = json.dumps(result_to_dict(result), ensure_ascii=False)
        row.closing_bank_minutes = result.bank_closed_minutes
        row.revision = (row.revision or 0) + 1
        row.closed_by_name, row.closed_at = self.actor, utcnow()
        self.db.flush()   # уникальный ключ (сотрудник, период) запрещает конкурентное повторное закрытие

    def load_result(self, employee_id: str, period: Period) -> dict | None:
        row = self._row(employee_id, period)
        return None if row is None else {"result": json.loads(row.result_json), "revision": row.revision,
                                         "closed_by": row.closed_by_name, "closed_at": row.closed_at.isoformat(),
                                         "versions": row.settings_versions.split(",")}


class SqlBankWrite:
    def __init__(self, db: Session):
        self.db = db

    def save_closing_bank(self, employee_id: str, period: Period, closing_minutes: int) -> None:
        row = self.db.scalar(select(PeriodClosing).where(PeriodClosing.employee_id == emp_pk(employee_id),
                                                         PeriodClosing.period_start == period.start))
        row.closing_bank_minutes = closing_minutes


class SqlCarryOver:
    def __init__(self, db: Session):
        self.db = db

    def load_deferred(self, employee_id: str, period: Period) -> list[DeferredBlock]:
        rows = self.db.scalars(select(DeferredCarry).where(DeferredCarry.employee_id == emp_pk(employee_id),
                                                           DeferredCarry.period_start == period.start)
                               .order_by(DeferredCarry.id))
        return [DeferredBlock(r.source_day, r.tariff, r.minutes, r.reason_code) for r in rows]

    def save_deferred(self, employee_id: str, next_period: Period, blocks: Sequence[DeferredBlock]) -> None:
        """Пересчёт заменяет исходящие переносы, а не дополняет их (7.3)."""
        self.db.execute(delete(DeferredCarry).where(DeferredCarry.employee_id == emp_pk(employee_id),
                                                    DeferredCarry.period_start == next_period.start))
        self.db.add_all([DeferredCarry(employee_id=emp_pk(employee_id), period_start=next_period.start,
                                       source_day=b.source_day, tariff=b.tariff, minutes=b.minutes,
                                       reason_code=b.reason_code) for b in blocks])
        self.db.flush()
