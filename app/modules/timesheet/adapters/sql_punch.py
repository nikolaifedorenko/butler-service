"""PunchPort поверх таблицы punches (Punch.ts — локальное naive-время объекта).

Обязанности адаптера (7.4): UTC-aware моменты; kind из источника; стабильный порядок
(ts, id); все отметки одного сотрудника; отметок позже now нет; допустимое чередование —
первая линия (санация источника: повторный «пришёл» отбрасывается, повторный «ушёл»
заменяется предыдущим); тип по позиции не восстанавливается, синтетические отметки
не подмешиваются. Вторая линия — ядро pair_marks (CHK-PUNCH-SEQUENCE)."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain.types.entities import Mark
from ._db import emp_pk, local_naive_to_utc, utc_to_local_naive
from .orm import Punch


def _mark(p: Punch) -> Mark:
    return Mark(str(p.employee_id), local_naive_to_utc(p.ts), "in" if p.kind == "IN" else "out")


def sanitize(marks: Sequence[Mark], opening: Mark | None) -> list[Mark]:
    """Первая линия контроля чередования (7.4 п.4): исправление данных — ответственность
    адаптера и источника (1.3); домен последовательность не чинит (R31)."""
    out: list[Mark] = []
    last_kind = opening.kind if opening is not None else "out"
    for m in marks:
        if m.kind == last_kind == "in":
            continue                      # повторный «пришёл» — держим первый
        if m.kind == last_kind == "out" and out:
            out[-1] = m                   # повторный «ушёл» — держим последний
            continue
        if m.kind == last_kind == "out":
            continue                      # «ушёл» без открытой сессии
        out.append(m)
        last_kind = m.kind
    return out


class SqlPunchAdapter:
    def __init__(self, db: Session, now: dt.datetime):
        self.db, self.now = db, now
        self._window: tuple[dt.datetime, dt.datetime] | None = None   # окно prefetch()
        self._pre_rows: dict[int, list[Punch]] = {}
        self._pre_before: dict[int, Punch | None] = {}

    def prefetch(self, employee_ids: Sequence[str], from_utc: dt.datetime,
                 to_utc: dt.datetime) -> None:
        """Отметки многих сотрудников за [from, to) и последняя до from — двумя запросами
        (Факт за месяц, PERF-02). marks_between и last_mark_before на этом окне берут их
        отсюда; фильтры те же, что в _rows и last_mark_before."""
        pks = [emp_pk(e) for e in employee_ids]
        hi = min(to_utc, self.now + dt.timedelta(microseconds=1))
        lo_n, hi_n, now_n = (utc_to_local_naive(x) for x in (from_utc, hi, self.now))
        rows: dict[int, list[Punch]] = {pk: [] for pk in pks}
        for p in self.db.scalars(select(Punch).where(
                Punch.employee_id.in_(pks), Punch.ts >= lo_n, Punch.ts < hi_n, Punch.ts <= now_n)
                .order_by(Punch.ts, Punch.id)):
            rows[p.employee_id].append(p)
        rank = func.row_number().over(partition_by=Punch.employee_id,
                                      order_by=(Punch.ts.desc(), Punch.id.desc())).label("rank")
        last = select(Punch.id, rank).where(Punch.employee_id.in_(pks), Punch.ts < lo_n,
                                            Punch.ts <= now_n).subquery()
        before = {p.employee_id: p for p in self.db.scalars(
            select(Punch).join(last, Punch.id == last.c.id).where(last.c.rank == 1))}
        self._window = (from_utc, hi)
        self._pre_rows = rows
        self._pre_before = {pk: before.get(pk) for pk in pks}

    def _rows(self, employee_id: str, lo: dt.datetime | None, hi: dt.datetime) -> list[Punch]:
        if self._window == (lo, hi) and emp_pk(employee_id) in self._pre_rows:
            return list(self._pre_rows[emp_pk(employee_id)])
        q = select(Punch).where(Punch.employee_id == emp_pk(employee_id),
                                Punch.ts < utc_to_local_naive(hi),
                                Punch.ts <= utc_to_local_naive(self.now))
        if lo is not None:
            q = q.where(Punch.ts >= utc_to_local_naive(lo))
        return list(self.db.scalars(q.order_by(Punch.ts, Punch.id)))

    def marks_between(self, employee_id: str, from_utc: dt.datetime,
                      to_utc: dt.datetime) -> list[Mark]:
        """[from, to) — отметка ровно на границе попадает ровно в одну выборку (2.6, v7/R7)."""
        hi = min(to_utc, self.now + dt.timedelta(microseconds=1))
        marks = [_mark(p) for p in self._rows(employee_id, from_utc, hi)]
        return sanitize(marks, self.last_mark_before(employee_id, from_utc))

    def last_mark_before(self, employee_id: str, at_utc: dt.datetime) -> Mark | None:
        """Строго at < at_utc (2.6)."""
        if self._window and at_utc == self._window[0] and emp_pk(employee_id) in self._pre_before:
            p = self._pre_before[emp_pk(employee_id)]
            return _mark(p) if p else None
        p = self.db.scalar(select(Punch).where(
            Punch.employee_id == emp_pk(employee_id),
            Punch.ts < utc_to_local_naive(at_utc),
            Punch.ts <= utc_to_local_naive(self.now))
            .order_by(Punch.ts.desc(), Punch.id.desc()).limit(1))
        return _mark(p) if p else None

    def first_mark_after(self, employee_id: str, at_utc: dt.datetime) -> Mark | None:
        """Первая отметка с at ≥ at_utc (2.6) — закрывает сессию за правой границей (16.4)."""
        p = self.db.scalar(select(Punch).where(
            Punch.employee_id == emp_pk(employee_id),
            Punch.ts >= utc_to_local_naive(at_utc),
            Punch.ts <= utc_to_local_naive(self.now))
            .order_by(Punch.ts, Punch.id).limit(1))
        return _mark(p) if p else None

    def last_marks(self, at_utc: dt.datetime) -> list[Mark]:
        """Батч (16.2): по одной последней отметке на сотрудника с at ≤ at_utc, один запрос.

        Последняя — по МОМЕНТУ (ts, id), а не по id создания: отметки задним числом
        (менеджер поправил забытый уход), сид и импорты пишут строки вне порядка ts.
        С MAX(id) доска показывала устаревший статус: сотрудник с закрытой сессией
        оставался «на работе» с более раннего «пришёл» (дефект 15.10.2026: расхождение
        доски с личным экраном, который смотрит по ts).
        """
        hi = utc_to_local_naive(min(at_utc, self.now))
        ranked = select(
            Punch.id,
            func.row_number().over(
                partition_by=Punch.employee_id,
                order_by=(Punch.ts.desc(), Punch.id.desc()),
            ).label("rn"),
        ).where(Punch.ts <= hi).subquery()
        rows = self.db.scalars(
            select(Punch).join(ranked, Punch.id == ranked.c.id)
            .where(ranked.c.rn == 1)
            .order_by(Punch.ts, Punch.id))
        return [_mark(p) for p in rows]
