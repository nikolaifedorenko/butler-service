"""PunchPort поверх таблицы punches (Punch.ts — локальное naive-время объекта)."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Punch
from ..domain.types.entities import Mark
from ._db import emp_pk, local_naive_to_utc, utc_to_local_naive


def _mark(p: Punch) -> Mark:
    return Mark(str(p.employee_id), local_naive_to_utc(p.ts), "in" if p.kind == "IN" else "out")


def sanitize(marks: Sequence[Mark], opening: Mark | None) -> list[Mark]:
    """Обязанность адаптера (7.4): допустимое чередование. Повторный «пришёл» без «ушёл»
    отбрасывается (держим первый приход), повторный «ушёл» заменяет предыдущий (держим последний)."""
    out: list[Mark] = []
    last_kind = opening.kind if opening else "out"
    for m in marks:
        if m.kind == last_kind == "in":
            continue
        if m.kind == last_kind == "out" and out:
            out[-1] = m
            continue
        if m.kind == last_kind == "out":
            continue
        out.append(m)
        last_kind = m.kind
    return out


class SqlPunchAdapter:
    def __init__(self, db: Session, now: dt.datetime):
        self.db, self.now = db, now

    def _rows(self, employee_id: str, lo: dt.datetime | None, hi: dt.datetime) -> list[Punch]:
        q = select(Punch).where(Punch.employee_id == emp_pk(employee_id), Punch.ts < utc_to_local_naive(hi))
        if lo is not None:
            q = q.where(Punch.ts >= utc_to_local_naive(lo))
        return list(self.db.scalars(q.order_by(Punch.ts, Punch.id)))

    def marks_between(self, employee_id: str, from_utc: dt.datetime, to_utc: dt.datetime) -> list[Mark]:
        hi = min(to_utc, self.now + dt.timedelta(microseconds=1))
        marks = [_mark(p) for p in self._rows(employee_id, from_utc, hi)]
        return sanitize(marks, self.last_mark_before(employee_id, from_utc))

    def last_mark_before(self, employee_id: str, at_utc: dt.datetime) -> Mark | None:
        p = self.db.scalar(select(Punch).where(Punch.employee_id == emp_pk(employee_id),
                                               Punch.ts < utc_to_local_naive(at_utc))
                           .order_by(Punch.ts.desc(), Punch.id.desc()).limit(1))
        return _mark(p) if p else None
