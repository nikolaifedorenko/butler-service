"""Приёмочные примеры EX-16…EX-30 (base 11)."""
from __future__ import annotations

from app.engine.domain.codes_registry.reason_codes import UNPAID_CREDITED

from .helpers import (
    IN,
    OUT,
    absence,
    adjustment,
    assert_bank,
    assert_cards,
    assert_cuts,
    assert_flags,
    assert_mgmt,
    assert_no_flags,
    at,
    d,
    day,
    double,
    period,
    run,
    run_settle,
    settings,
    unpaid,
)

OCT1_2 = period(d(1), d(2))


# ── EX-16 · Переработка не оплачивается → в банк по весу ──────────────────────

def test_ex_16_unpaid_overtime_to_bank_by_weight():
    prd = period(d(1), d(1))
    st = settings([double(1), unpaid(1)])
    result = run_settle(prd, [day(1, "В")], [IN(1, 8), OUT(1, 20)], st=st)
    assert_cards(result, [(d(1), 0, 0, 0)])
    assert_mgmt(result, {d(1): ""})
    assert_bank(result, closed=24, credited=24)
    credited = [r for r in result.trace if r.code == UNPAID_CREDITED]
    assert len(credited) == 1
    assert dict(credited[0].data) == {"day": d(1), "tariff": "ДЯ2", "taken_minutes": 720,
                                      "credited_minutes": 1440}


# ── EX-17 · Та же переработка гасит недостачу другого дня ─────────────────────

def test_ex_17_unpaid_covers_other_day_debt():
    st = settings([double(1), unpaid(1)])
    rows = [day(1, "В"), day(2, "Я 12")]
    result, flags = run(OCT1_2, rows, [IN(1, 8), OUT(1, 20)], st=st, with_flags=True)
    assert_cards(result, [(d(1), 0, 0, 0), (d(2), 12, 0, 12)])
    assert_mgmt(result, {d(1): "", d(2): ""})
    assert_bank(result, closed=12, credited=24, paid=12, total_debt=12, residual=0)
    assert_flags(flags, [(d(1), "OFF_SHIFT_ATTENDANCE", None, None, at(1, 8)),
                         (d(2), "LATE", (2, 8, 0), None)])


# ── EX-18 · Ручная корректировка банка ────────────────────────────────────────

def test_ex_18_manual_bank_adjustment():
    prd = period(d(1), d(1))
    result = run_settle(prd, [day(1, "Я 12")], [IN(1, 8), OUT(1, 20)],
                        adjustments=[adjustment(-240, prd)])
    assert_cards(result, [(d(1), 12, 12, 0)])
    assert_mgmt(result, {d(1): ""})
    assert_bank(result, closed=-4, adjustments=-4)


# ── EX-19 · Пустой день внутри открытой сессии ────────────────────────────────

def test_ex_19_empty_day_inside_open_session():
    prd = period(d(5), d(7))
    rows = [day(5, "В"), day(6, "В"), day(7, "В")]
    result = run_settle(prd, rows, [IN(5, 20), OUT(7, 8)])
    assert_cards(result, [(d(5), 0, 0, 0), (d(6), 0, 0, 0), (d(7), 0, 0, 0)])
    assert_mgmt(result, {d(5): "ДЯ 2, ДН 2", d(6): "ДН 8, ДЯ 16", d(7): "ДН 6, ДЯ 2"})
    assert_bank(result, closed=0)


# ── EX-20 · Режим просмотра против закрытия ───────────────────────────────────

def _ex20():
    return [day(1, "Я 12"), day(2, "В")], [IN(1, 20), OUT(2, 20)]


def test_ex_20_view_mode():
    rows, marks = _ex20()
    result = run_settle(OCT1_2, rows, marks, mode="view", now=at(3, 0))
    assert_cards(result, [(d(1), 12, 0, 12), (d(2), 0, 0, 0)])
    assert_mgmt(result, {d(1): "ДЯ 2, ДН 2", d(2): "ДЯ 14, ДН 6"})
    assert_bank(result, closed=0, paid=0, total_debt=12, residual=12)
    assert result.cuts == ()


def test_ex_20_close_mode():
    rows, marks = _ex20()
    result = run_settle(OCT1_2, rows, marks)
    assert_cards(result, [(d(1), 12, 0, 12), (d(2), 0, 0, 0)])
    assert_mgmt(result, {d(1): "ДН 2", d(2): "ДЯ 4, ДН 6"})
    assert_bank(result, closed=0, paid=0, total_debt=12, residual=0)
    assert sum(c.taken_minutes for c in result.cuts) == 720


# ── EX-21 · Гранула дороже остатка долга ──────────────────────────────────────

def test_ex_21_granule_more_expensive_than_rest():
    st = settings([double(2)])
    result = run_settle(OCT1_2, [day(1, "Я 12"), day(2, "В")],
                        [IN(1, 8), OUT(1, 19), IN(2, 22), OUT(2, 24)], st=st)
    assert_cards(result, [(d(1), 12, 11, 1), (d(2), 0, 0, 0)])
    assert_mgmt(result, {d(1): "", d(2): "ДН2 2"})
    assert_bank(result, closed=-1, total_debt=1, paid=0, residual=1)
    assert result.cuts == ()


# ── EX-22 · Гранула влезает в долг ровно ──────────────────────────────────────

def test_ex_22_granule_fits_exactly():
    st = settings([double(2)])
    result = run_settle(OCT1_2, [day(1, "Я 12"), day(2, "В")],
                        [IN(1, 8), OUT(1, 18), IN(2, 20), OUT(2, 21)], st=st)
    assert_cards(result, [(d(1), 12, 10, 2), (d(2), 0, 0, 0)])
    assert_mgmt(result, {d(1): "", d(2): ""})
    assert_bank(result, closed=0, total_debt=2, paid=0, residual=0)
    assert_cuts(result, [(d(2), d(2), "ДЯ2", 60, 120)])


# ── EX-23 · Долг 3 ч, кода 2 ч ────────────────────────────────────────────────

def test_ex_23_debt_3h_code_2h():
    st = settings([double(2)])
    result = run_settle(OCT1_2, [day(1, "Я 12"), day(2, "В")],
                        [IN(1, 8), OUT(1, 17), IN(2, 20), OUT(2, 22)], st=st)
    assert_cards(result, [(d(1), 12, 9, 3), (d(2), 0, 0, 0)])
    assert_mgmt(result, {d(1): "", d(2): "ДЯ2 1"})
    assert_bank(result, closed=-1, total_debt=3, paid=0, residual=1)
    assert_cuts(result, [(d(2), d(2), "ДЯ2", 60, 120)])


# ── EX-24 · Очередь CFG-CASCADE решает ────────────────────────────────────────

def test_ex_24_cascade_order_decides():
    prd = period(d(1), d(3))
    st = settings([double(3)])
    marks = [IN(1, 8), OUT(1, 18), IN(2, 20), OUT(2, 22), IN(3, 20), OUT(3, 21)]
    result = run_settle(prd, [day(1, "Я 12"), day(2, "В"), day(3, "В")], marks, st=st)
    assert_cards(result, [(d(1), 12, 10, 2), (d(2), 0, 0, 0), (d(3), 0, 0, 0)])
    assert_mgmt(result, {d(1): "", d(2): "", d(3): "ДЯ2 1"})
    assert_bank(result, closed=0, total_debt=2, paid=0, residual=0)
    assert_cuts(result, [(d(2), d(2), "ДЯ", 120, 120)])


# ── EX-25 · Минус банка на входе ──────────────────────────────────────────────

def test_ex_25_negative_bank_on_input():
    prd = period(d(1), d(1))
    result, flags = run(prd, [day(1, "Я 12")], [], bank=-60, with_flags=True)
    assert_cards(result, [(d(1), 12, 0, 12)])
    assert_bank(result, closed=-13, open_=-1, total_debt=13, paid=0, residual=13)
    assert result.cuts == ()
    assert_flags(flags, [(d(1), "LATE", (1, 8, 0), None)])


# ── EX-26 · Долг 1 ч, дешёвый и дорогой код ───────────────────────────────────

def test_ex_26_cheap_and_expensive_code():
    prd = period(d(1), d(3))
    st = settings([double(3)])
    marks = [IN(1, 8), OUT(1, 19), IN(2, 20), OUT(2, 21), IN(3, 20), OUT(3, 21)]
    result = run_settle(prd, [day(1, "Я 12"), day(2, "В"), day(3, "В")], marks, st=st)
    assert_cards(result, [(d(1), 12, 11, 1), (d(2), 0, 0, 0), (d(3), 0, 0, 0)])
    assert_mgmt(result, {d(1): "", d(2): "", d(3): "ДЯ2 1"})
    assert_bank(result, closed=0, total_debt=1, paid=0, residual=0)
    assert_cuts(result, [(d(2), d(2), "ДЯ", 60, 60)])


# ── EX-27 · Каскад: банк, код, остаток ────────────────────────────────────────

def test_ex_27_cascade_bank_code_rest():
    st = settings([double(2)])
    result = run_settle(OCT1_2, [day(1, "Я 12"), day(2, "В")],
                        [IN(1, 8), OUT(1, 13), IN(2, 21), OUT(2, 23)], bank=240, st=st)
    assert_cards(result, [(d(1), 12, 5, 7), (d(2), 0, 0, 0)])
    assert_mgmt(result, {d(1): "", d(2): "ДН2 1"})
    assert_bank(result, closed=-1, total_debt=7, paid=4, residual=1)
    assert_cuts(result, [(d(2), d(2), "ДЯ2", 60, 120)])


# ── EX-28 · Сотрудник не отметился «ушёл» ────────────────────────────────────

def test_ex_28_case_a_past_day_clipped_by_horizon():
    prd = period(d(1), d(1))
    result = run_settle(prd, [day(1, "Я 12")], [IN(1, 8)], mode="view", now=at(2, 9))
    assert_cards(result, [(d(1), 12, 12, 0)])
    assert_mgmt(result, {d(1): "ДЯ 2, ДН 2"})
    assert_bank(result, closed=0, paid=0, total_debt=0, residual=0)


def test_ex_28_case_b_current_day_ends_at_now_calc():
    prd = period(d(1), d(1))
    result = run_settle(prd, [day(1, "Я 12")], [IN(1, 8)], mode="view", now=at(1, 18))
    assert_cards(result, [(d(1), 12, 10, 2)])
    assert_mgmt(result, {d(1): ""})
    assert_bank(result, closed=0, paid=0, total_debt=2, residual=2)


# ── EX-29 · Выходной за часы (полное покрытие смены) ─────────────────────────

def test_ex_29_day_off_for_hours_full_coverage():
    prd = period(d(5), d(5))
    result, flags = run(prd, [day(5, "Я 12")], [],
                        absences=[absence(at(5, 8), at(5, 20))], with_flags=True)
    assert_cards(result, [(d(5), 12, 0, 12)])
    assert_mgmt(result, {d(5): ""})
    assert_bank(result, closed=-12, total_debt=12, residual=12)
    assert_no_flags(flags)


# ── EX-30 · Вход EX-29, но сотрудник пришёл 08:00–20:00 ───────────────────────

def test_ex_30_came_anyway_off_shift_attendance():
    prd = period(d(5), d(5))
    result, flags = run(prd, [day(5, "Я 12")], [IN(5, 8), OUT(5, 20)],
                        absences=[absence(at(5, 8), at(5, 20))], with_flags=True)
    assert_cards(result, [(d(5), 12, 12, 0)])
    assert_mgmt(result, {d(5): ""})
    assert_bank(result, closed=0)
    assert_flags(flags, [(d(5), "OFF_SHIFT_ATTENDANCE", None, None, at(5, 8))])
    off = flags.flags[0]
    assert off.data["day_code"] == "Я"
    assert off.data["absence_intervals"] == ((at(5, 8), at(5, 20)),)
    assert off.data["shift_segments"] == ((at(5, 8), at(5, 20)),)
