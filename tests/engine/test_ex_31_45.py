"""Приёмочные примеры EX-31…EX-45 (base 11)."""
from __future__ import annotations

import datetime as dt

import pytest

from app.modules.timesheet.domain.codes_registry.reason_codes import CODE_PLACED, PLAN_EQUALS_FACT
from app.modules.timesheet.domain.settings.resolve_modifier import resolve_modifier
from app.modules.timesheet.domain.settings.types import (
    MOD_DOUBLE,
    MOD_PAYS,
    ModifierEntry,
    Window,
)
from app.modules.timesheet.domain.settings.validate import validate_settings
from app.modules.timesheet.domain.types.entities import Day
from app.modules.timesheet.domain.types.errors import ConfigError, IncompletePeriodError

from .helpers import (
    IN,
    OUT,
    PEF_AUTO_,
    absence,
    assert_bank,
    assert_cards,
    assert_deferred,
    assert_exceptions,
    assert_flags,
    assert_mgmt,
    assert_no_flags,
    at,
    d,
    day,
    deferred,
    double,
    not_in_ut,
    pef,
    period,
    run,
    run_settle,
    settings,
    shift,
)

Y = 2026


def _windows_1075():
    from app.modules.timesheet.domain.settings.defaults import default_settings
    windows = dict(default_settings().windows)
    windows["Я 10,75"] = Window(8 * 60, 20 * 60)
    return windows


# ── EX-31 · Согласованное отсутствие в середине смены ─────────────────────────

def test_ex_31_absence_in_middle_of_shift():
    prd = period(d(5), d(5))
    marks = [IN(5, 8), OUT(5, 11, 40), IN(5, 15, 30), OUT(5, 20)]
    result, flags = run(prd, [day(5, "Я 12")], marks,
                        absences=[absence(at(5, 12), at(5, 15))], with_flags=True)
    assert_cards(result, [(d(5), 12, 8, 4)])
    assert_mgmt(result, {d(5): ""})
    assert_bank(result, closed=-4, total_debt=4, paid=0, residual=4)
    assert result.cuts == ()
    assert_flags(flags, [(d(5), "LATE", (5, 15, 0), (5, 15, 30)),
                         (d(5), "EARLY_DEPARTURE", (5, 12, 0), (5, 11, 40))])


def test_ex_31_control_absence_in_window_debt_from_window():
    prd = period(d(1), d(1))
    st = settings(windows=_windows_1075())
    marks = [IN(1, 7), OUT(1, 12), IN(1, 15), OUT(1, 23)]
    result, flags = run(prd, [day(1, "Я 10,75")], marks, bank=300, st=st,
                        now=at(2, 0), absences=[absence(at(1, 12), at(1, 15))],
                        with_flags=True)
    assert_cards(result, [(d(1), 12, 9, 3)])       # план карточки = 720 (v7.1/R34)
    assert result.cards[0].full_fact_minutes == 780
    assert_mgmt(result, {d(1): "ДЯ 3, ДН 1"})
    assert_bank(result, closed=2, total_debt=3, paid=3, residual=0)
    assert result.cuts == ()                        # банк раньше кодов (CFG-CASCADE)
    assert_no_flags(flags)                          # уход/возврат ровно по границам


# ── EX-32 · Несколько отсутствий в дне ────────────────────────────────────────

def test_ex_32_several_absences_in_day():
    prd = period(d(5), d(5))
    marks = [IN(5, 8, 10), OUT(5, 10), IN(5, 11), OUT(5, 13, 40), IN(5, 15), OUT(5, 20)]
    absences = [absence(at(5, 10), at(5, 11)), absence(at(5, 14), at(5, 15))]
    result, flags = run(prd, [day(5, "Я 12")], marks, absences=absences, with_flags=True)
    assert_cards(result, [(d(5), 12, 10, 2)])
    assert_mgmt(result, {d(5): ""})
    assert_bank(result, closed=-2, total_debt=2, residual=2)
    assert_flags(flags, [(d(5), "LATE", (5, 8, 0), (5, 8, 10)),
                         (d(5), "EARLY_DEPARTURE", (5, 14, 0), (5, 13, 40))])


# ── EX-33 · «Не пришёл» ───────────────────────────────────────────────────────

def test_ex_33_did_not_come():
    prd = period(d(1), d(1))
    result, flags = run(prd, [day(1, "Я 12")], [], with_flags=True)
    assert_cards(result, [(d(1), 12, 0, 12)])
    assert_mgmt(result, {d(1): ""})
    assert_bank(result, closed=-12, total_debt=12, residual=12)
    assert_flags(flags, [(d(1), "LATE", (1, 8, 0), None)])


def test_ex_33_control_presence_outside_subintervals():
    prd = period(d(1), d(1))
    result, flags = run(prd, [day(1, "Я 12")], [IN(1, 6), OUT(1, 7)], mode="view",
                        now=at(1, 23), with_flags=True)
    assert_cards(result, [(d(1), 12, 0, 12)])
    assert_mgmt(result, {d(1): "ДЯ 1"})
    assert_bank(result, closed=0, total_debt=12, paid=0, residual=12)
    assert_flags(flags, [(d(1), "LATE", (1, 8, 0), None)])   # OFF_SHIFT не ставится


# ── EX-34 · Забытый уход: непрерывное присутствие несколько суток ─────────────

def _ex34_rows():
    return [Day(dt.date(Y, 10, 30), "Я", 720, "e1", "Смена 1"),
            Day(dt.date(Y, 10, 31), "Я", 720, "e1", "Смена 1"),
            Day(dt.date(Y, 11, 1), "Я", 720, "e1", "Смена 1"),
            Day(dt.date(Y, 11, 2), "Я", 720, "e1", "Смена 1")]


_EX34_PERIOD = period(dt.date(Y, 10, 30), dt.date(Y, 11, 2))
_D30, _D31 = dt.date(Y, 10, 30), dt.date(Y, 10, 31)
_N1, _N2 = dt.date(Y, 11, 1), dt.date(Y, 11, 2)


def test_ex_34_forgotten_out_view():
    marks = [IN(30, 8)]
    result, flags = run(_EX34_PERIOD, _ex34_rows(), marks, mode="view",
                        now=at(1, 12, month=11), with_flags=True)
    assert_cards(result, [(_D30, 12, 12, 0), (_D31, 12, 12, 0), (_N1, 12, 4, 8), (_N2, 12, 0, 12)])
    assert_mgmt(result, {_D30: "ДЯ 2, ДН 2", _D31: "ДН 8, ДЯ 4", _N1: "ДН 6, ДЯ 2", _N2: ""})
    assert_bank(result, closed=0, total_debt=20, paid=0, residual=20)
    assert result.cuts == ()
    assert_no_flags(flags)


def test_ex_34_forgotten_out_close():
    marks = [IN(30, 8)]
    result = run_settle(_EX34_PERIOD, _ex34_rows(), marks, mode="close",
                        now=at(3, 0, month=11))
    assert_cards(result, [(_D30, 12, 12, 0), (_D31, 12, 12, 0), (_N1, 12, 12, 0), (_N2, 12, 12, 0)])
    assert_mgmt(result, {_D30: "ДЯ 2, ДН 2", _D31: "ДН 8, ДЯ 4", _N1: "ДН 8, ДЯ 4", _N2: "ДН 8, ДЯ 4"})
    assert sum(c.full_fact_minutes for c in result.cards) == 88 * 60
    assert_bank(result, closed=0, total_debt=0, paid=0, residual=0)
    assert result.cuts == ()


# ── EX-35 · Долг дня гасится банком, коды остаются ───────────────────────────

def test_ex_35_day_debt_paid_by_bank_codes_stay():
    prd = period(d(1), d(3))
    st = settings([double(1)])
    marks = [IN(1, 20), OUT(2, 8)]
    rows = [day(1, "Я 12"), day(2, "ОТ"), day(3, "В")]
    result = run_settle(prd, rows, marks, bank=1200, st=st)
    assert_cards(result, [(d(1), 12, 0, 12), (d(2), 0, 0, 0), (d(3), 0, 0, 0)])
    assert_mgmt(result, {d(1): "ДЯ2 2, ДН2 2", d(2): "", d(3): "ДН 6, ДЯ 2"})
    assert_bank(result, closed=8, total_debt=12, paid=12, residual=0)
    assert result.cuts == ()


# ── EX-36 · Отложенный блок из прошлого периода ───────────────────────────────

def test_ex_36_deferred_from_previous_period():
    prd = period(d(1), d(3))
    rows = [day(1, "Я 12"), day(2, "В"), day(3, "В")]
    result = run_settle(prd, rows, [IN(1, 8), OUT(1, 20)],
                        deferred=[deferred(dt.date(Y, 9, 29), "ДН", 360)])
    assert_cards(result, [(d(1), 12, 12, 0), (d(2), 0, 0, 0), (d(3), 0, 0, 0)])
    assert_mgmt(result, {d(1): "ДН 6", d(2): "", d(3): ""})
    assert_bank(result, closed=0)
    assert_deferred(result, [])
    placed = [r for r in result.trace if r.code == CODE_PLACED]
    assert [(r.step, r.data["pass"]) for r in placed] == [("placement", "primary")]


def test_ex_36_control_receiver_with_plan_equals_fact_capacity_from_window():
    prd = period(d(1), d(2))
    st = settings([pef(PEF_AUTO_, 2)])
    rows = [day(1, "ОТ"), day(2, "К 12")]
    result, flags = run(prd, rows, [], st=st, now=at(3, 0),
                        deferred=[deferred(dt.date(Y, 9, 29), "ДН", 780)], with_flags=True)
    assert_cards(result, [(d(1), 0, 0, 0), (d(2), 0, 0, 0)])
    assert result.cards[1].plan_equals_fact_applied is True
    assert_mgmt(result, {d(1): "", d(2): "ДН 12"})
    assert_deferred(result, [(dt.date(Y, 9, 29), "ДН", 60)])
    assert_exceptions(result, ["NO_RECEIVER"])
    pef_records = [r for r in result.trace if r.code == PLAN_EQUALS_FACT]
    assert pef_records[0].data["policy"] == "auto_code"
    assert_no_flags(flags)                      # LATE(None) подавлен «План=Факт»
    # INV-MINUTES-CONSERVED: 780 = 720 + 60 — обеспечивается check_result внутри settle


# ── EX-37 · Отложенный блок не находит приёмника ──────────────────────────────

def test_ex_37_deferred_without_receiver():
    prd = period(d(1), d(2))
    rows = [day(1, "Я 12"), day(2, "Я 12")]
    result, flags = run(prd, rows, [IN(1, 0)], now=at(3, 0),
                        deferred=[deferred(dt.date(Y, 9, 29), "ДН", 720)], with_flags=True)
    assert_cards(result, [(d(1), 12, 12, 0), (d(2), 12, 12, 0)])
    assert_mgmt(result, {d(1): "ДН 8, ДЯ 4", d(2): "ДН 8, ДЯ 4"})
    assert_deferred(result, [(dt.date(Y, 9, 29), "ДН", 720)])
    assert_exceptions(result, ["NO_RECEIVER"])
    assert_bank(result, closed=0)
    assert_no_flags(flags)


# ── EX-38 · Отметка за границей периода после округления ──────────────────────

def test_ex_38_mark_beyond_period_after_rounding():
    prd = period(dt.date(Y, 10, 31), dt.date(Y, 10, 31))
    marks = [IN(31, 20), Mark_out_nov1()]
    result = run_settle(prd, [day(31, "В")], marks, now=at(1, 12, month=11))
    assert_cards(result, [(dt.date(Y, 10, 31), 0, 0, 0)])
    assert_mgmt(result, {dt.date(Y, 10, 31): "ДЯ 2, ДН 2"})
    assert_bank(result, closed=0)


def Mark_out_nov1():
    return OUT(1, 0, 20, month=11)


# ── EX-39 · Округление now ────────────────────────────────────────────────────

def test_ex_39_now_rounding_case_a():
    prd = period(d(1), d(1))
    result, flags = run(prd, [day(1, "Я 12")], [IN(1, 15, 40)], mode="view",
                        now=at(1, 15, 45), with_flags=True)
    assert_cards(result, [(d(1), 12, 0, 12)])
    assert result.cards[0].full_fact_minutes == 0
    assert_mgmt(result, {d(1): ""})
    assert_flags(flags, [(d(1), "LATE", (1, 8, 0), (1, 15, 40))])


def test_ex_39_now_rounding_case_b():
    prd = period(d(1), d(1))
    result, flags = run(prd, [day(1, "Я 12")], [IN(1, 15, 40)], mode="view",
                        now=at(1, 23, 40), with_flags=True)
    assert_cards(result, [(d(1), 12, 4, 8)])
    assert_mgmt(result, {d(1): "ДЯ 2, ДН 2"})
    assert_flags(flags, [(d(1), "LATE", (1, 8, 0), (1, 15, 40))])


def test_ex_39_case_c_close_before_midnight_rejected():
    prd = period(d(1), d(1))
    with pytest.raises(IncompletePeriodError):
        run_settle(prd, [day(1, "Я 12")], [IN(1, 15, 40)], mode="close", now=at(1, 23, 40))


# ── EX-40 · Флаги смены через полночь по исходному присутствию ────────────────

_EX40_SHIFTS = [shift(at(1, 20), at(2, 8))]


def test_ex_40_night_shift_flags_by_raw_presence():
    rows = [day(1, "В"), day(2, "В")]
    marks = [IN(1, 20, 3), OUT(2, 7, 58)]
    result, flags = run(OCT1_2_PRD(), rows, marks, shifts=_EX40_SHIFTS, with_flags=True)
    assert_cards(result, [(d(1), 0, 0, 0), (d(2), 0, 0, 0)])
    assert_mgmt(result, {d(1): "ДЯ 2, ДН 2", d(2): "ДН 6, ДЯ 2"})
    assert_bank(result, closed=0)
    assert_no_flags(flags)


def OCT1_2_PRD():
    return period(d(1), d(2))


def test_ex_40_variant_late_over_limit():
    rows = [day(1, "В"), day(2, "В")]
    marks = [IN(1, 20, 20), OUT(2, 7, 58)]
    result, flags = run(OCT1_2_PRD(), rows, marks, shifts=_EX40_SHIFTS, with_flags=True)
    assert_mgmt(result, {d(1): "ДЯ 2, ДН 2", d(2): "ДН 6, ДЯ 2"})
    assert_flags(flags, [(d(1), "LATE", (1, 20, 0), (1, 20, 20))])


# ── EX-41 · Конкуренция блоков за ёмкость (CFG-PLACEMENT) ─────────────────────

def _ex41():
    rows = [day(1, "ОТ"), day(2, "Я 12")]
    marks = [IN(1, 18), OUT(2, 0), IN(2, 2), OUT(3, 0)]
    return rows, marks


def test_ex_41_blocks_compete_for_capacity():
    rows, marks = _ex41()
    result = run_settle(OCT1_2_PRD(), rows, marks, now=at(3, 0))
    assert_cards(result, [(d(1), 0, 0, 0), (d(2), 12, 12, 0)])
    assert_mgmt(result, {d(1): "", d(2): "ДН 6, ДЯ 6"})
    assert_deferred(result, [(d(1), "ДЯ", 120), (d(1), "ДН", 120)])
    assert_exceptions(result, ["NO_RECEIVER", "NO_RECEIVER"])
    assert_bank(result, closed=0)


def test_ex_41_variant_placement_order_changed():
    rows, marks = _ex41()
    st = settings(placement_order=("ДН", "ДЯ", "ДЯ2", "ДН2"))
    result = run_settle(OCT1_2_PRD(), rows, marks, st=st, now=at(3, 0))
    assert_mgmt(result, {d(1): "", d(2): "ДН 8, ДЯ 4"})
    assert_deferred(result, [(d(1), "ДЯ", 240)])


# ── EX-42 · Исключённый из УТ день → банк ─────────────────────────────────────

def test_ex_42_excluded_from_ut_goes_to_bank():
    prd = period(d(4), d(5))
    st = settings([not_in_ut(4)])
    marks = [IN(4, 8), OUT(4, 12), IN(5, 10), OUT(5, 12)]
    result, flags = run(prd, [day(4, "В"), day(5, "Б")], marks, st=st, with_flags=True)
    assert_cards(result, [(d(4), 0, 0, 0), (d(5), 0, 0, 0)])
    assert_mgmt(result, {d(4): "", d(5): ""})
    assert_bank(result, closed=6, credited=6)
    assert_flags(flags, [(d(4), "OFF_SHIFT_ATTENDANCE", None, None, at(4, 8)),
                         (d(5), "OFF_SHIFT_ATTENDANCE", None, None, at(5, 10))])


def test_ex_42_variant_double():
    prd = period(d(4), d(5))
    st = settings([not_in_ut(4), double(4)])
    marks = [IN(4, 8), OUT(4, 12), IN(5, 10), OUT(5, 12)]
    result = run_settle(prd, [day(4, "В"), day(5, "Б")], marks, st=st)
    assert_mgmt(result, {d(4): "", d(5): ""})
    assert_bank(result, closed=10, credited=10)


# ── EX-43 · Чужой блок пропускает исключённый день ────────────────────────────

def test_ex_43_foreign_block_skips_excluded_day():
    prd = period(d(1), d(3))
    st = settings([not_in_ut(2)])
    marks = [IN(1, 20), OUT(1, 22)]
    rows = [day(1, "ОТ"), day(2, "В"), day(3, "В")]
    result = run_settle(prd, rows, marks, st=st)
    assert_cards(result, [(d(1), 0, 0, 0), (d(2), 0, 0, 0), (d(3), 0, 0, 0)])
    assert_mgmt(result, {d(1): "", d(2): "", d(3): "ДЯ 2"})
    assert_bank(result, closed=0)
    assert_deferred(result, [])


# ── EX-44 · Граница окна не на сетке шага ─────────────────────────────────────

def test_ex_44_window_off_grid_step_60():
    st = settings(windows={**dict(_base_windows()), "Я 9": Window(9 * 60 + 30, 18 * 60 + 30)})
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    assert any(code == "CHK-GRID" for code, _ in exc.value.violations)


def _base_windows():
    from app.modules.timesheet.domain.settings.defaults import default_settings
    return default_settings().windows


def test_ex_44_window_off_grid_step_30_ok():
    st = settings(step_minutes=30,
                  windows={**dict(_base_windows()), "Я 9": Window(9 * 60 + 30, 18 * 60 + 30)})
    validate_settings(st)


def test_ex_44_control_fractional_plan_not_violation():
    st = settings(windows=_windows_1075())
    validate_settings(st)                    # «Я 10,75»: план 645 вне сетки — норма


# ── EX-45 · Некорректные записи модификаторов CFG-MODIFIERS ───────────────────

def test_ex_45_control_1_modifier_scope():
    entry = ModifierEntry(MOD_PAYS, True, employee_id="e1", group="Смена 1", day=d(7))
    with pytest.raises(ConfigError) as exc:
        validate_settings(settings([entry]))
    assert any(code == "CHK-MODIFIER-SCOPE" for code, _ in exc.value.violations)


def test_ex_45_control_2_modifier_type():
    entry = ModifierEntry(MOD_PAYS, "yes", day=d(7))
    with pytest.raises(ConfigError) as exc:
        validate_settings(settings([entry]))
    assert any(code == "CHK-MODIFIER-TYPE" for code, _ in exc.value.violations)


def test_ex_45_control_3_modifier_conflict():
    entries = [ModifierEntry(MOD_PAYS, True, employee_id="e1", day=d(7)),
               ModifierEntry(MOD_PAYS, False, employee_id="e1", day=d(7))]
    with pytest.raises(ConfigError) as exc:
        validate_settings(settings(entries))
    assert any(code == "CHK-MODIFIER-CONFLICT" for code, _ in exc.value.violations)


def test_ex_45_control_3_conflict_even_with_equal_values():
    entries = [ModifierEntry(MOD_PAYS, True, employee_id="e1", day=d(7)),
               ModifierEntry(MOD_PAYS, True, employee_id="e1", day=d(7))]
    with pytest.raises(ConfigError):
        validate_settings(settings(entries))


def test_ex_45_control_4_per_day_partial_period_is_norm():
    prd_oct = period(dt.date(Y, 10, 15), dt.date(Y, 10, 31))
    entry = ModifierEntry(MOD_DOUBLE, True, period=prd_oct)
    st = settings([entry])
    validate_settings(st)                     # конфликта нет
    day14 = Day(dt.date(Y, 10, 14), "В", 0, "e1", "Смена 1")
    day15 = Day(dt.date(Y, 10, 15), "В", 0, "e1", "Смена 1")
    assert resolve_modifier(MOD_DOUBLE, day14, st) is False   # глобальный дефолт
    assert resolve_modifier(MOD_DOUBLE, day15, st) is True    # запись периода
