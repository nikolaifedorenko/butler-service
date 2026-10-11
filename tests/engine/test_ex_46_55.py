"""Приёмочные примеры EX-46…EX-54 (base 11). EX-53 и EX-55 — application-уровень
(пересчёт закрытого периода, эффективный период) — в test_application.py."""
from __future__ import annotations

import datetime as dt

import pytest

from app.engine.domain.codes_registry.reason_codes import OPENING_ROUNDED
from app.engine.domain.settings.types import Window
from app.engine.domain.types.errors import InvalidInputDataError

from .helpers import (
    IN,
    OUT,
    PEF_AUTO_,
    absence,
    assert_bank,
    assert_cards,
    assert_cuts,
    assert_deferred,
    assert_exceptions,
    assert_flags,
    assert_mgmt,
    assert_no_flags,
    at,
    d,
    day,
    deferred,
    pef,
    period,
    run,
    run_settle,
    settings,
    shift,
)

Y = 2026
SEP29 = dt.date(Y, 9, 29)


def _windows_1075():
    from app.engine.domain.settings.defaults import default_settings
    windows = dict(default_settings().windows)
    windows["Я 10,75"] = Window(8 * 60, 20 * 60)
    return windows


# ── EX-46 · Повторное размещение после каскада ────────────────────────────────

def _ex46():
    prd = period(d(1), d(3))
    rows = [day(1, "Я 12"), day(2, "ОТ"), day(3, "Я 12")]
    marks = [IN(1, 8), OUT(1, 18), IN(2, 22), OUT(3, 0), IN(3, 0), OUT(4, 0)]
    return prd, rows, marks


def test_ex_46_replacement_after_cascade_close():
    prd, rows, marks = _ex46()
    result = run_settle(prd, rows, marks, now=at(4, 0))
    assert_cards(result, [(d(1), 12, 10, 2), (d(2), 0, 0, 0), (d(3), 12, 12, 0)])
    assert_mgmt(result, {d(1): "", d(2): "", d(3): "ДН 10, ДЯ 2"})
    assert_bank(result, closed=0, total_debt=2, paid=0, residual=0)
    assert_cuts(result, [(d(3), d(3), "ДЯ", 120, 120)])
    assert_deferred(result, [])
    after = [r for r in result.trace if r.code == "CODE_PLACED" and r.data["pass"] == "after_cascade"]
    assert len(after) == 1
    assert after[0].step == "replacement"
    assert after[0].data["placed_day"] == d(3)


def test_ex_46_view_no_cut():
    prd, rows, marks = _ex46()
    result = run_settle(prd, rows, marks, mode="view", now=at(4, 0))
    assert_cards(result, [(d(1), 12, 10, 2), (d(2), 0, 0, 0), (d(3), 12, 12, 0)])
    assert_mgmt(result, {d(1): "", d(2): "", d(3): "ДН 8, ДЯ 4"})
    assert result.cuts == ()
    assert_deferred(result, [(d(2), "ДН", 120)])
    assert_bank(result, paid=0, total_debt=2, residual=2, closed=0)


# ── EX-47 · Коллизия округления не меняет порядок отметок ─────────────────────

def test_ex_47_rounding_collision_keeps_order():
    prd = period(d(1), d(1))
    marks = [IN(1, 7), OUT(1, 8, 10), IN(1, 8, 20), OUT(1, 9)]
    result = run_settle(prd, [day(1, "Я 12")], marks, mode="view", now=at(2, 0))
    assert_cards(result, [(d(1), 12, 1, 11)])
    assert result.cards[0].full_fact_minutes == 120
    assert_mgmt(result, {d(1): "ДЯ 1"})
    assert_bank(result, closed=0, total_debt=11, paid=0, residual=11)


def test_ex_47_control_resorted_marks_would_raise():
    """Контроль: пересортировка «пришёл раньше ушёл» при равенстве моментов дала бы
    нарушение чередования — домен так делать не должен (4.5, 12.22)."""
    from app.engine.domain.sessions.pair_marks import pair_marks
    from app.engine.domain.settings.defaults import default_settings
    from app.engine.domain.time.to_calc_mark import to_calc_mark

    st = default_settings()
    marks = [IN(1, 7), OUT(1, 8, 10), IN(1, 8, 20), OUT(1, 9)]
    calc = [to_calc_mark(m, st) for m in marks]
    assert len(pair_marks(calc)) == 2                   # правильный порядок — две сессии
    with pytest.raises(InvalidInputDataError) as exc:
        pair_marks([calc[0], calc[2], calc[1], calc[3]])  # ошибочная пересортировка
    assert exc.value.code == "CHK-PUNCH-SEQUENCE"


# ── EX-48 · «План=Факт»: событие присутствия при нулевом факте ────────────────

def test_ex_48_presence_event_with_zero_fact():
    prd = period(d(1), d(1))
    st = settings([pef(PEF_AUTO_, 1)])
    result = run_settle(prd, [day(1, "К 12")], [IN(1, 8, 10), OUT(1, 8, 20)], st=st,
                        mode="view", now=at(2, 0))
    assert_cards(result, [(d(1), 12, 0, 12)])
    assert result.cards[0].plan_equals_fact_applied is False
    assert_mgmt(result, {d(1): ""})
    assert not [r for r in result.trace if r.code == "PLAN_EQUALS_FACT"]


def test_ex_48_control_no_marks_applied():
    prd = period(d(1), d(1))
    st = settings([pef(PEF_AUTO_, 1)])
    result = run_settle(prd, [day(1, "К 12")], [], st=st, mode="view", now=at(2, 0))
    assert_cards(result, [(d(1), 0, 0, 0)])
    assert result.cards[0].plan_equals_fact_applied is True
    pef_records = [r for r in result.trace if r.code == "PLAN_EQUALS_FACT"]
    assert len(pef_records) == 1
    assert pef_records[0].data["policy"] == "auto_code"


# ── EX-49 · Секундная граница допуска ─────────────────────────────────────────

def _ex49(marks):
    prd = period(d(1), d(1))
    return run(prd, [day(1, "Я 12")], marks, mode="view", now=at(1, 23), with_flags=True)


def test_ex_49_second_boundary_late():
    result, flags = _ex49([IN(1, 8, 5, 1), OUT(1, 20, 0, 0)])
    assert_cards(result, [(d(1), 12, 12, 0)])
    assert_flags(flags, [(d(1), "LATE", (1, 8, 0), (1, 8, 5, 1))])


def test_ex_49_control_1_exactly_on_limit():
    result, flags = _ex49([IN(1, 8, 5, 0), OUT(1, 20)])
    assert_cards(result, [(d(1), 12, 12, 0)])
    assert_no_flags(flags)


def test_ex_49_control_2_before_limit():
    result, flags = _ex49([IN(1, 8, 4, 59), OUT(1, 20)])
    assert_cards(result, [(d(1), 12, 12, 0)])
    assert_no_flags(flags)


# ── EX-50 · Схлоп короткой сессии на полуночи ─────────────────────────────────

def test_ex_50_short_session_collapse_at_midnight():
    prd = period(d(1), d(2))
    result = run_settle(prd, [day(1, "В"), day(2, "В")], [IN(1, 23, 40), OUT(1, 23, 50)],
                        mode="view", now=at(3, 0))
    assert_cards(result, [(d(1), 0, 0, 0), (d(2), 0, 0, 0)])
    # регрессия: запрещены факт 24 ч и коды ДН 8 + ДЯ 16 на 02.10
    assert all(c.full_fact_minutes == 0 for c in result.cards)
    assert all(dict(c.codes) == {} for c in result.cards)
    assert_mgmt(result, {d(1): "", d(2): ""})
    assert_bank(result, closed=0)


# ── EX-51 · План меньше длины окна: рабочее время и недостача — по окну ───────

def _ex51_run(marks, prd=None, rows=None, bank=0, now=None):
    prd = prd or period(d(1), d(1))
    rows = rows if rows is not None else [day(1, "Я 10,75")]
    st = settings(windows=_windows_1075())
    return run_settle(prd, rows, marks, bank=bank, st=st,
                      now=now or at(2, 0))


def test_ex_51_control_1_full_shift():
    result = _ex51_run([IN(1, 8), OUT(1, 20)])
    assert_cards(result, [(d(1), 12, 12, 0)])
    assert result.cards[0].full_fact_minutes == 720
    assert_mgmt(result, {d(1): ""})
    assert_bank(result, closed=0)


def test_ex_51_control_2_stayed_later():
    result = _ex51_run([IN(1, 8), OUT(1, 21)])
    assert_cards(result, [(d(1), 12, 12, 0)])
    assert result.cards[0].full_fact_minutes == 780
    assert_mgmt(result, {d(1): "ДЯ 1"})


def test_ex_51_control_3_left_earlier():
    result = _ex51_run([IN(1, 8), OUT(1, 19)])
    assert_cards(result, [(d(1), 12, 11, 1)])
    assert_bank(result, closed=-1)


def test_ex_51_control_4_one_hour_presence():
    result = _ex51_run([IN(1, 12), OUT(1, 13)])
    assert_cards(result, [(d(1), 12, 1, 11)])
    assert_bank(result, closed=-11)


def test_ex_51_control_5_left_in_middle_of_window():
    result = _ex51_run([IN(1, 8), OUT(1, 12)])
    assert_cards(result, [(d(1), 12, 4, 8)])
    assert_bank(result, closed=-8)


def test_ex_51_control_6_broken_presence():
    result = _ex51_run([IN(1, 8), OUT(1, 13), IN(1, 14), OUT(1, 20)])
    assert_cards(result, [(d(1), 12, 11, 1)])
    assert_bank(result, closed=-1)


def test_ex_51_control_7_grid_multiplicity():
    result = _ex51_run([IN(1, 8), OUT(1, 19)])
    card = result.cards[0]
    step = 60
    assert card.plan_minutes % step == 0
    assert card.work_minutes % step == 0
    assert card.overtime_minutes % step == 0
    assert card.debt_minutes % step == 0
    assert card.timesheet_value == "Я 10,75"      # информационный план 645 — вне сетки


def test_ex_51_control_8_transfer_capacity_from_window():
    prd = period(d(1), d(2))
    rows = [day(1, "ОТ"), Day2_1075()]
    marks = [IN(1, 8), OUT(1, 21), IN(2, 8), OUT(2, 20)]
    st = settings(windows=_windows_1075())
    result, flags = run(prd, rows, marks, st=st, now=at(3, 0), with_flags=True)
    assert_cards(result, [(d(1), 0, 0, 0), (d(2), 12, 12, 0)])
    assert_mgmt(result, {d(1): "", d(2): "ДЯ 12"})
    assert_deferred(result, [(d(1), "ДЯ", 60)])
    assert_exceptions(result, ["NO_RECEIVER"])
    assert_bank(result, closed=0)
    assert_flags(flags, [(d(1), "OFF_SHIFT_ATTENDANCE", None, None, at(1, 8))])


def Day2_1075():
    return day(2, "Я 10,75")


# ── EX-52 · Смена шага расчёта: нормализация входящих остатков ────────────────

def _ex52(bank, prev_step, deferred_in, marks):
    prd = period(d(1), d(2))
    rows = [day(1, "Я 12"), day(2, "В")]
    return run_settle(prd, rows, marks, bank=bank, deferred=deferred_in,
                      prev_step=prev_step, now=at(3, 0))


def test_ex_52_step_change_normalization():
    result = _ex52(45, 15, [deferred(SEP29, "ДН", 75), deferred(SEP29, "ДЯ", 15)],
                   [IN(1, 8), OUT(1, 20)])
    assert_cards(result, [(d(1), 12, 12, 0), (d(2), 0, 0, 0)])
    assert_mgmt(result, {d(1): "ДН 1", d(2): ""})
    assert result.bank_open_minutes == 45
    assert result.bank_open_normalized_minutes == 60
    assert result.bank_closed_minutes == 60
    assert_deferred(result, [])
    rounded = [r for r in result.trace if r.code == OPENING_ROUNDED]
    assert len(rounded) == 3
    assert [r.data["kind"] for r in rounded] == ["bank", "deferred_block", "deferred_block"]
    assert dict(rounded[0].data) == {"kind": "bank", "before_minutes": 45, "after_minutes": 60,
                                     "delta_minutes": 15, "old_step_minutes": 15,
                                     "new_step_minutes": 60}
    # канонический порядок блоков: ДЯ раньше ДН (CFG-PLACEMENT)
    assert (rounded[1].data["tariff"], rounded[1].data["before_minutes"],
            rounded[1].data["after_minutes"]) == ("ДЯ", 15, 0)
    assert (rounded[2].data["tariff"], rounded[2].data["before_minutes"],
            rounded[2].data["after_minutes"]) == ("ДН", 75, 60)


def test_ex_52_control_1_exact_half_rounds_away_from_zero():
    result = _ex52(30, 15, [deferred(SEP29, "ДН", 75), deferred(SEP29, "ДЯ", 15)],
                   [IN(1, 8), OUT(1, 20)])
    assert result.bank_open_normalized_minutes == 60
    assert result.bank_closed_minutes == 60


def test_ex_52_control_2_negative_bank_and_debt():
    result, flags = run(period(d(1), d(2)), [day(1, "Я 12"), day(2, "В")], [],
                        bank=-45, prev_step=15, now=at(3, 0), with_flags=True)
    assert result.bank_open_normalized_minutes == -60
    assert_cards(result, [(d(1), 12, 0, 12), (d(2), 0, 0, 0)])
    assert_bank(result, total_debt=13, paid=0, residual=13, closed=-13)
    assert_mgmt(result, {d(1): "", d(2): ""})
    assert_flags(flags, [(d(1), "LATE", (1, 8, 0), None)])


def test_ex_52_control_3_step_unchanged_no_normalization():
    result = _ex52(45, 60, [deferred(SEP29, "ДН", 60)], [IN(1, 8), OUT(1, 20)])
    assert result.bank_open_normalized_minutes == 45
    assert_mgmt(result, {d(1): "ДН 1", d(2): ""})
    assert result.bank_closed_minutes == 45
    assert not [r for r in result.trace if r.code == OPENING_ROUNDED]


# ── EX-54 · Ночная графиковая смена и отсутствие через полночь ────────────────

def test_ex_54_night_schedule_shift_and_absence_over_midnight():
    prd = period(d(1), d(2))
    st = settings(windows=_windows_1075())
    rows = [day(1, "Я 10,75"), day(2, "Я 10,75")]
    marks = [IN(1, 20), OUT(1, 23), IN(2, 3), OUT(2, 20)]
    shifts = [shift(at(1, 20), at(2, 8)), shift(at(2, 8), at(2, 20))]
    absences = [absence(at(1, 23), at(2, 3))]
    result, flags = run(prd, rows, marks, bank=300, st=st, now=at(3, 0),
                        shifts=shifts, absences=absences, with_flags=True)
    assert_cards(result, [(d(1), 12, 0, 12), (d(2), 12, 12, 0)])
    assert_mgmt(result, {d(1): "", d(2): "ДН 1"})
    assert_bank(result, closed=0, total_debt=12, paid=5, residual=0)
    assert_cuts(result, [(d(1), d(1), "ДЯ", 120, 120), (d(2), d(2), "ДЯ", 120, 120),
                         (d(1), d(1), "ДН", 60, 60), (d(2), d(2), "ДН", 120, 120)])
    assert_deferred(result, [])
    assert_no_flags(flags)
