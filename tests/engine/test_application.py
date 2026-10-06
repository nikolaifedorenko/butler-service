"""Application-слой (13.14): выборка 7.4, атомарность закрытия, повторное закрытие, пересчёт."""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.engine.adapters.clock import FixedClock
from app.engine.application.close_period import close_period
from app.engine.application.context import EnginePorts
from app.engine.application.errors import PeriodAlreadyClosedError, RecalculationForbiddenError
from app.engine.application.periods import month_period, next_period
from app.engine.application.recalculate import recalculate
from app.engine.application.view_period import view_period
from app.engine.ports.settlement_store import ClosingInputs, PeriodState

from .helpers import EMP, IN, OUT, DeferredBlock, at, d, day, settings


@dataclass
class Memory:
    days: list
    marks: list
    bank_open: int = 0
    deferred: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)
    banks: dict = field(default_factory=dict)
    snapshots: dict = field(default_factory=dict)
    fail_on_bank: bool = False
    calls: list = field(default_factory=list)


class Ports:
    def __init__(self, m: Memory):
        self.m = m

    # TimesheetPort
    def days(self, eid, period):
        return [x for x in self.m.days if period.start <= x.day <= period.end]

    # PunchPort
    def marks_between(self, eid, lo, hi):
        self.m.calls.append(("marks_between", lo, hi))
        return [x for x in self.m.marks if lo <= x.at_utc < hi]

    def last_mark_before(self, eid, at_utc):
        prior = [x for x in self.m.marks if x.at_utc < at_utc]
        return prior[-1] if prior else None

    def shifts(self, eid, period):
        return []

    def absences(self, eid, period):
        return []

    def opening(self, eid, period):
        return self.m.bank_open

    def adjustments(self, eid, period):
        return []

    def load(self, period):
        return settings()

    def load_deferred(self, eid, period):
        return self.m.deferred.get(period.start, [])

    def save_deferred(self, eid, nxt, blocks):
        self.m.deferred[nxt.start] = list(blocks)

    def save_result(self, eid, period, result, snap, versions, step, replace):
        self.m.results[period.start] = result
        self.m.snapshots[period.start] = snap

    def period_state(self, eid, period):
        return PeriodState(period.start in self.m.results, any(k > period.end for k in self.m.results))

    def closing_inputs(self, eid, period):
        return self.m.snapshots.get(period.start)

    def previous_step(self, eid, period):
        return None

    def save_closing_bank(self, eid, period, minutes):
        if self.m.fail_on_bank:
            raise RuntimeError("сбой записи банка")
        self.m.banks[period.start] = minutes


class TxMemory:
    """UnitOfWork для памяти: снимок при входе, откат при исключении."""

    def __init__(self, m: Memory):
        self.m = m

    def __enter__(self):
        self.snap = (dict(self.m.results), dict(self.m.banks), dict(self.m.deferred), dict(self.m.snapshots))
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.m.results, self.m.banks, self.m.deferred, self.m.snapshots = (dict(x) for x in self.snap)


def ports_of(m: Memory, now) -> EnginePorts:
    p = Ports(m)
    return EnginePorts(timesheet=p, punch=p, shift=p, absence=p, bank=p, settings=p, carry_over=p, store=p,
                       bank_write=p, unit_of_work=lambda: TxMemory(m), clock=FixedClock(now))


OCT = month_period(2026, 10)
NOV = next_period(OCT)


def oct_days():
    return [day(i, "В") for i in range(1, 32)]


def test_f32_application_builds_window_with_margin():
    m = Memory(oct_days(), [IN(31, 20), OUT(1, 0, 20, month=11)])
    view = view_period(EMP, OCT, ports_of(m, at(1, 12, month=11)))
    last = view.settle.cards[-1]
    assert last.codes == {"ДЯ": 120, "ДН": 120} and not last.open_at_end
    lo, hi = m.calls[0][1], m.calls[0][2]
    assert lo == at(30, 23, month=9) and hi == at(1, 1, month=11)


def test_close_is_atomic():
    m = Memory(oct_days(), [IN(1, 8), OUT(1, 20)], fail_on_bank=True)
    with pytest.raises(RuntimeError):
        close_period(EMP, OCT, ports_of(m, at(1, 0, month=11)))
    assert m.results == {} and m.banks == {} and m.deferred == {}


def test_double_close_forbidden_and_deferred_saved_exactly():
    m = Memory([day(31, "ОТ")], [IN(31, 8), OUT(31, 10)])
    view = close_period(EMP, OCT, ports_of(m, at(1, 0, month=11)))
    assert m.deferred[NOV.start] == list(view.settle.deferred_blocks) == [DeferredBlock(d(31), "ДЯ", 120, "NO_RECEIVER")]
    with pytest.raises(PeriodAlreadyClosedError):
        close_period(EMP, OCT, ports_of(m, at(1, 0, month=11)))


def test_recalculate_only_last_closed_and_replaces_carry():
    m = Memory([day(31, "ОТ")] + [day(i, "В", month=11) for i in range(1, 31)], [IN(31, 8), OUT(31, 10)])
    p = ports_of(m, at(1, 0, month=12))
    close_period(EMP, OCT, p)
    m.days[0] = day(31, "В")                          # правка Табеля последнего закрытого периода
    recalculate(EMP, OCT, p)
    assert m.deferred[NOV.start] == []                # переносы заменены, а не дополнены
    close_period(EMP, NOV, p)
    with pytest.raises(RecalculationForbiddenError):
        recalculate(EMP, OCT, p)


def test_recalculate_starts_from_snapshot():
    m = Memory(oct_days(), [IN(1, 8), OUT(1, 20)], bank_open=300)
    p = ports_of(m, at(1, 0, month=11))
    close_period(EMP, OCT, p)
    m.bank_open = 9999                                  # входящий банк изменился «потом»
    view = recalculate(EMP, OCT, p)
    assert view.settle.bank_open_minutes == 300
    assert m.snapshots[OCT.start] == ClosingInputs(300, (), 60)
