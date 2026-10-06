"""Юнит-тесты функций каталога 8 на граничных случаях (13.3) и неделимость изъятия (13.8)."""
from __future__ import annotations

import datetime as dt
from dataclasses import replace

import pytest

from app.engine.domain.bank.minutes_to_cut import minutes_to_cut
from app.engine.domain.bank.pay_with_bank import pay_debt_with_bank
from app.engine.domain.day_card.split_by_category import split_by_category
from app.engine.domain.opening.normalize_bank import normalize_opening_bank
from app.engine.domain.opening.normalize_deferred import normalize_deferred
from app.engine.domain.opening.round_signed import round_signed
from app.engine.domain.presence.day_intervals import day_intervals
from app.engine.domain.presence.end_minute_of_day import end_minute_of_day
from app.engine.domain.time.day_of_moment import day_of_moment
from app.engine.domain.time.round_moment import round_moment
from app.engine.domain.time.to_calc_mark import to_calc_mark
from app.engine.domain.types.entities import DeferredBlock, Interval

from .helpers import EMP, IN, OUT, Mark, at, d, day, run, settings

ST = settings()


def test_round_half_up_and_midnight_rule():
    assert round_moment(at(1, 8, 30), 60, ST.tz) == at(1, 9)
    assert round_moment(at(1, 8, 29), 60, ST.tz) == at(1, 8)
    assert round_moment(at(1, 8, 7, ), 15, ST.tz) == at(1, 8)
    assert round_moment(at(1, 8, 7) + dt.timedelta(seconds=30), 15, ST.tz) == at(1, 8, 15)
    m = to_calc_mark(IN(1, 23, 35), ST)
    assert m.day == d(2) and m.at_calc == at(2, 0)
    assert day_of_moment(at(2, 0), "out", ST.tz) == d(1)
    assert day_of_moment(at(2, 0), "in", ST.tz) == d(2)


def test_day_intervals_open_closed_and_empty():
    assert day_intervals((), "closed", d(1), 1440, ST.tz) == ((), "closed")
    assert day_intervals((), "open", d(1), 1440, ST.tz) == ((Interval(d(1), 0, 1440),), "open")
    marks = (to_calc_mark(OUT(1, 8), ST), to_calc_mark(IN(1, 20), ST))
    got, state = day_intervals(marks, "open", d(1), 1440, ST.tz)
    assert got == (Interval(d(1), 0, 480), Interval(d(1), 1200, 1440)) and state == "open"


def test_end_minute_today_future_and_now_calc_midnight():
    assert end_minute_of_day(d(1), d(2), at(2, 5), ST.tz) == 1440
    assert end_minute_of_day(d(3), d(2), at(2, 5), ST.tz) == 0
    assert end_minute_of_day(d(2), d(2), at(2, 5), ST.tz) == 300
    assert end_minute_of_day(d(2), d(2), at(3, 0), ST.tz) == 1440


def test_category_boundaries_06_22():
    assert split_by_category(Interval(d(1), 300, 420), ST) == {"ДН": 60, "ДЯ": 60}
    assert split_by_category(Interval(d(1), 1260, 1380), ST) == {"ДЯ": 60, "ДН": 60}


def test_future_day_in_view_is_forecast():
    r = run([day(1, "Я 12"), day(2, "Я 12")], [IN(1, 8), OUT(1, 20)], mode="view", now=at(1, 21))
    assert [c.debt_minutes for c in r.cards] == [0, 720]


def test_round_signed_examples():
    assert [round_signed(v, 60) for v in (15, 30, -15, -30)] == [0, 60, 0, -60]


def test_normalize_on_step_change():
    v, rs = normalize_opening_bank(-90, 30, 60)
    assert v == -120 and rs[0].data["delta_minutes"] == -30
    assert normalize_opening_bank(45, 60, 60) == (45, ())
    blocks, rs = normalize_deferred([DeferredBlock(d(1), "ДЯ", 15, "x"), DeferredBlock(d(1), "ДН", 45, "x")], 15, 60)
    assert [b.minutes for b in blocks] == [60] and len(rs) == 2


@pytest.mark.parametrize("step", [15, 30, 60])
def test_cut_is_indivisible(step):
    assert minutes_to_cut(rest=3 * step, weight=2, available=10 * step, step=step) == step
    assert minutes_to_cut(rest=step - 1, weight=1, available=10 * step, step=step) == 0
    assert minutes_to_cut(rest=10 * step, weight=1, available=3 * step, step=step) == 3 * step


def test_pay_with_bank():
    assert pay_debt_with_bank(5, 3) == (3, 2, 0)
    assert pay_debt_with_bank(5, -3) == (0, 5, 0)


def test_schedule_changes_only_flags():
    from app.engine.domain.flags.evaluate_flags import evaluate_flags
    from .helpers import shift, absence, period_of, close_now
    days = [day(1, "Я 12")]
    r = run(days, [IN(1, 9), OUT(1, 20)])
    a = evaluate_flags(period_of(days), days, r.cards, [IN(1, 9), OUT(1, 20)], None, [shift(1, 8, 1, 20)], [],
                       ST, close_now(period_of(days)))
    b = evaluate_flags(period_of(days), days, r.cards, [IN(1, 9), OUT(1, 20)], None, [shift(1, 9, 1, 21)],
                       [absence(1, 9, 10)], ST, close_now(period_of(days)))
    assert a != b
    assert run(days, [IN(1, 9), OUT(1, 20)]) == r


def test_naive_now_rejected():
    with pytest.raises(ValueError):
        run([day(1, "В")], now=dt.datetime(2026, 10, 2))
    assert EMP and Mark and replace
