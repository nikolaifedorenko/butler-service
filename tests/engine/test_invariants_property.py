"""Инварианты И1–И19 на случайных входах (property-based) и И10 — детерминированность."""
from __future__ import annotations

import datetime as dt
from dataclasses import replace

from hypothesis import HealthCheck, given, settings as hsettings, strategies as s

from app.engine.domain.flags.evaluate_flags import evaluate_flags
from app.engine.domain.pipeline.settle import settle
from app.engine.domain.types.entities import Adjustment, DeferredBlock, Period

from .helpers import EMP, TZ, UTC, Mark, d, day, double, not_in_ut, settings, unpaid

VALUES = ["Я 12", "Я 9", "Я 8", "К 12", "В", "ДО", "ОТ", "ОВ", "Б", "НБ", "НН", "Н 4", "Н 8", "Н 12"]
TARIFFS = ["ДЯ", "ДН", "ДЯ 2", "ДН 2"]
N = 6


@s.composite
def scenario(draw):
    step = draw(s.sampled_from([15, 30, 60]))
    values = draw(s.lists(s.sampled_from(VALUES), min_size=N, max_size=N))
    days = [day(i + 1, v) for i, v in enumerate(values)]
    minutes = sorted(set(draw(s.lists(s.integers(0, N * 1440 + 90), max_size=10))))
    first_kind = draw(s.sampled_from(["in", "out"]))
    base = dt.datetime(2026, 10, 1, tzinfo=TZ).astimezone(UTC)
    kinds = [("in", "out")[(i + (first_kind == "out")) % 2] for i in range(len(minutes))]
    marks = [Mark(EMP, base + dt.timedelta(minutes=m), k) for m, k in zip(minutes, kinds)]
    mods = [f(i + 1) for i in range(N) for f, on in zip((double, unpaid, not_in_ut),
                                                       draw(s.lists(s.booleans(), min_size=3, max_size=3))) if on]
    deferred = [DeferredBlock(dt.date(2026, 9, 28), t, draw(s.integers(1, 8)) * step, "NO_RECEIVER")
                for t in draw(s.lists(s.sampled_from(TARIFFS), max_size=2, unique=True))]
    bank = draw(s.integers(-20, 20)) * 60
    adj = [Adjustment(draw(s.integers(-10, 10)) * 60, "manual")]
    prev = draw(s.sampled_from([15, 30, 60]))
    now_shift = draw(s.integers(0, N * 1440 + 120))
    return step, days, marks, mods, deferred, bank, adj, prev, base + dt.timedelta(minutes=now_shift)


def _run(sc, mode):
    step, days, marks, mods, deferred, bank, adj, prev, now = sc
    st = replace(settings(*mods), step_minutes=step)
    period = Period(d(1), d(N))
    if mode == "close":
        now = dt.datetime(2026, 10, N + 1, tzinfo=TZ).astimezone(UTC)
    else:
        marks = [m for m in marks if m.at_utc <= now]
    return settle(period, days, marks, None, bank, adj, deferred, st, now, mode, prev), (period, days, marks, st, now)


@hsettings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(scenario(), s.sampled_from(["view", "close"]))
def test_invariants_hold_and_deterministic(sc, mode):
    """Каждый прогон проверяет И1–И19 внутри settle(); здесь — И10 и И16 через evaluate_flags."""
    r1, (period, days, marks, st, now) = _run(sc, mode)
    r2, _ = _run(sc, mode)
    assert r1 == r2                                   # И10
    evaluate_flags(period, days, r1.cards, marks, None, [], [], st, now)
    step = st.step_minutes
    assert all(b.minutes > 0 and b.minutes % step == 0 for b in r1.deferred_blocks)
    assert all(c.taken_minutes % step == 0 for c in r1.cuts)
