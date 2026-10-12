"""Приёмочные примеры EX-01…EX-15 (base 11): каждый подкейс — отдельный тест,
полное сравнение SettleResult и, где указано, FlagsResult в канонической форме (3.4)."""
from __future__ import annotations

import datetime as dt

import pytest

from app.engine.domain.codes_registry.reason_codes import (
    CODE_PLACED,
    PLAN_EQUALS_FACT,
)
from app.engine.domain.settings.checks.window_key import CHK_WINDOW_KEY
from app.engine.domain.settings.checks.window_plan import CHK_WINDOW_PLAN
from app.engine.domain.settings.types import Window
from app.engine.domain.types.errors import ConfigError, InvalidInputDataError

from .helpers import (
    IN,
    OUT,
    PEF_AUTO_,
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
    double,
    pef,
    period,
    run,
    run_settle,
    settings,
    shift,
)

Y = 2026
OCT1_2 = period(d(1), d(2))


# ── EX-01 · Суточная смена через полночь, на обоих днях «Двойные переработки» ──

def _ex01_inputs():
    rows = [day(1, "Я 12"), day(2, "В")]
    st = settings([double(1), double(2)])
    marks = [IN(1, 8), OUT(2, 8)]
    return rows, st, marks


def test_ex_01_daily_shift_over_midnight_double():
    rows, st, marks = _ex01_inputs()
    result, flags = run(OCT1_2, rows, marks, st=st, shifts=[shift(at(1, 8), at(2, 8))],
                        with_flags=True)
    assert_cards(result, [(d(1), 12, 12, 0), (d(2), 0, 0, 0)])
    assert_mgmt(result, {d(1): "ДЯ2 2, ДН2 2", d(2): "ДН2 6, ДЯ2 2"})
    assert_bank(result, closed=0, total_debt=0, residual=0, paid=0)
    assert result.cuts == ()
    assert_no_flags(flags)


# ── EX-02 · Вечерняя суточная: недостача 12 ч и каскад ─────────────────────────

def test_ex_02_evening_daily_debt_and_cascade():
    rows = [day(1, "Я 12"), day(2, "В")]
    result = run_settle(OCT1_2, rows, [IN(1, 20), OUT(2, 20)])
    assert_cards(result, [(d(1), 12, 0, 12), (d(2), 0, 0, 0)])
    assert_mgmt(result, {d(1): "ДН 2", d(2): "ДН 6, ДЯ 4"})
    assert_bank(result, closed=0, total_debt=12, paid=0, residual=0)
    assert_cuts(result, [(d(1), d(1), "ДЯ", 120, 120), (d(2), d(2), "ДЯ", 600, 600)])


# ── EX-03 · Несколько сессий в одном дне ──────────────────────────────────────

def _ex03_inputs(bank):
    rows = [day(1, "Я 12"), day(2, "Я 12")]
    st = settings([double(2)])
    marks = [IN(1, 5), OUT(1, 10), IN(1, 19), OUT(2, 3), IN(2, 8), OUT(2, 23)]
    return rows, st, marks, bank


def test_ex_03_several_sessions_in_day():
    rows, st, marks, bank = _ex03_inputs(0)
    result = run_settle(OCT1_2, rows, marks, bank=bank, st=st)
    assert_cards(result, [(d(1), 12, 3, 9), (d(2), 12, 12, 0)])
    assert_mgmt(result, {d(1): "", d(2): "ДН2 4, ДЯ2 1"})
    assert_bank(result, closed=0, total_debt=9, paid=0, residual=0)
    assert_cuts(result, [(d(1), d(1), "ДЯ", 240, 240), (d(1), d(1), "ДН", 180, 180),
                         (d(2), d(2), "ДЯ2", 60, 120)])


# ── EX-04 · Вход EX-03 с банком 2 ч ───────────────────────────────────────────

def test_ex_04_bank_pays_part_double_codes_kept():
    rows, st, marks, _ = _ex03_inputs(0)
    result = run_settle(OCT1_2, rows, marks, bank=120, st=st)
    assert_cards(result, [(d(1), 12, 3, 9), (d(2), 12, 12, 0)])
    assert_mgmt(result, {d(1): "", d(2): "ДН2 4, ДЯ2 2"})
    assert_bank(result, closed=0, total_debt=9, paid=2, residual=0)
    assert_cuts(result, [(d(1), d(1), "ДЯ", 240, 240), (d(1), d(1), "ДН", 180, 180)])


# ── EX-05 · Каскад из настроек ────────────────────────────────────────────────

def test_ex_05_cascade_from_settings():
    rows = [day(1, "Я 12"), day(2, "В"), day(3, "В")]
    st = settings([double(3)])
    marks = [IN(1, 8), OUT(1, 10), IN(2, 20), OUT(3, 0), IN(3, 21), OUT(4, 0)]
    prd = period(d(1), d(3))
    result = run_settle(prd, rows, marks, bank=120, st=st)
    assert_cards(result, [(d(1), 12, 2, 10), (d(2), 0, 0, 0), (d(3), 0, 0, 0)])
    assert_mgmt(result, {d(1): "", d(2): "", d(3): "ДН2 1"})
    assert_bank(result, closed=0, total_debt=10, paid=2, residual=0)
    assert_cuts(result, [(d(2), d(2), "ДЯ", 120, 120), (d(2), d(2), "ДН", 120, 120),
                         (d(3), d(3), "ДЯ2", 60, 120), (d(3), d(3), "ДН2", 60, 120)])


# ── EX-06 · Перенос с дня, не принимающего коды УТ ────────────────────────────

def _ex06_inputs():
    rows = [day(1, "Я 12"), day(2, "ОТ"), day(3, "В")]
    marks = [IN(1, 8), OUT(2, 8, 2)]
    return rows, marks, period(d(1), d(3))


def test_ex_06_transfer_from_non_accepting_day():
    rows, marks, prd = _ex06_inputs()
    result, flags = run(prd, rows, marks, with_flags=True)
    assert_cards(result, [(d(1), 12, 12, 0), (d(2), 0, 0, 0), (d(3), 0, 0, 0)])
    assert_mgmt(result, {d(1): "ДЯ 2, ДН 2", d(2): "", d(3): "ДН 6, ДЯ 2"})
    assert_bank(result, closed=0)
    assert_deferred(result, [])
    assert [(f.step, f.code) for f in result.trace].count(("placement", CODE_PLACED)) == 2
    assert_flags(flags, [(d(2), "OFF_SHIFT_ATTENDANCE", None, None)])
    off = flags.flags[0]
    assert off.data["first_presence_at"] == at(2, 0)      # синтетическая граница 00:00
    assert off.data["day_code"] == "ОТ"


# ── EX-07 · Приёмника в периоде нет ───────────────────────────────────────────

def test_ex_07_no_receiver_in_period():
    rows = [day(1, "Я 12"), day(2, "ОТ")]
    result = run_settle(OCT1_2, rows, [IN(1, 8), OUT(2, 8, 2)])
    assert_cards(result, [(d(1), 12, 12, 0), (d(2), 0, 0, 0)])
    assert_mgmt(result, {d(1): "ДЯ 2, ДН 2", d(2): ""})
    assert_bank(result, closed=0)
    assert_deferred(result, [(d(2), "ДЯ", 120), (d(2), "ДН", 360)])
    assert_exceptions(result, ["NO_RECEIVER", "NO_RECEIVER"])


# ── EX-08 · Работа в выходной, которого нет в Графике ─────────────────────────

def test_ex_08_weekend_work_not_in_schedule():
    prd = period(d(3), d(3))
    result, flags = run(prd, [day(3, "В")], [IN(3, 8), OUT(3, 20)], with_flags=True)
    assert_cards(result, [(d(3), 0, 0, 0)])
    assert_mgmt(result, {d(3): "ДЯ 12"})
    assert_bank(result, closed=0)
    assert_flags(flags, [(d(3), "OFF_SHIFT_ATTENDANCE", None, None)])
    off = flags.flags[0]
    assert off.data["first_presence_at"] == at(3, 8)
    assert off.data["day_code"] == "В"
    assert off.data["shift_segments"] == ()


# ── EX-09 · Опоздал на час, ушёл позже, «Двойные переработки» ─────────────────

def test_ex_09_late_left_later_double():
    prd = period(d(1), d(1))
    result, flags = run(prd, [day(1, "Я 12")], [IN(1, 9, 15), OUT(1, 23, 35)], bank=360,
                        st=settings([double(1)]), with_flags=True)
    assert_cards(result, [(d(1), 12, 11, 1)])
    assert_mgmt(result, {d(1): "ДЯ2 2, ДН2 2"})
    assert_bank(result, closed=5, total_debt=1, paid=1, residual=0)
    assert result.cuts == ()
    assert_flags(flags, [(d(1), "LATE", (1, 8, 0), (1, 9, 15))])


# ── EX-10 · Недостача больше банка и кодов ────────────────────────────────────

def test_ex_10_debt_exceeds_bank_and_codes():
    result, flags = run(OCT1_2, [day(1, "Я 12"), day(2, "Я 12")], [], bank=180,
                        with_flags=True)
    assert_cards(result, [(d(1), 12, 0, 12), (d(2), 12, 0, 12)])
    assert_mgmt(result, {d(1): "", d(2): ""})
    assert_bank(result, closed=-21, total_debt=24, paid=3, residual=21)
    assert result.cuts == ()
    assert_flags(flags, [(d(1), "LATE", (1, 8, 0), None), (d(2), "LATE", (2, 8, 0), None)])


# ── EX-11 · Лимит 24 ч: перенос пропускает заполненный день ───────────────────

def test_ex_11_day_limit_skips_full_day():
    rows = [day(1, "ОТ"), day(2, "Я 12"), day(3, "В")]
    marks = [IN(1, 8), OUT(1, 20), IN(2, 0), OUT(3, 0)]
    prd = period(d(1), d(3))
    result, flags = run(prd, rows, marks, with_flags=True)
    assert_cards(result, [(d(1), 0, 0, 0), (d(2), 12, 12, 0), (d(3), 0, 0, 0)])
    assert_mgmt(result, {d(1): "", d(2): "ДН 8, ДЯ 4", d(3): "ДЯ 12"})
    assert_bank(result, closed=0)
    assert_deferred(result, [])
    assert_flags(flags, [(d(1), "OFF_SHIFT_ATTENDANCE", None, None)])


# ── EX-12 · Некорректная длина окна ───────────────────────────────────────────

def _windows_with(key: str, window: Window) -> dict:
    from app.engine.domain.settings.defaults import default_settings
    windows = dict(default_settings().windows)
    windows[key] = window
    return windows


def test_ex_12_wrong_window_length():
    from app.engine.domain.settings.validate import validate_settings
    st = settings(windows=_windows_with("Я 12", Window(8 * 60, 14 * 60)))
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    assert any(code == CHK_WINDOW_PLAN for code, _ in exc.value.violations)


def test_ex_12_control_non_canonical_window_key_dot():
    from app.engine.domain.settings.validate import validate_settings
    st = settings(windows=_windows_with("Я 10.75", Window(8 * 60, 20 * 60)))
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    assert any(code == CHK_WINDOW_KEY for code, _ in exc.value.violations)


def test_ex_12_control_non_canonical_window_key_no_space():
    from app.engine.domain.settings.validate import validate_settings
    st = settings(windows=_windows_with("Я12", Window(8 * 60, 20 * 60)))
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    assert any(code == CHK_WINDOW_KEY for code, _ in exc.value.violations)


# ── EX-13 · «План=Факт» ───────────────────────────────────────────────────────

def test_ex_13_plan_equals_fact_base():
    prd = period(d(1), d(1))
    st = settings([pef("yes", 1)])
    result, flags = run(prd, [day(1, "Я 12")], [], st=st, with_flags=True)
    card = result.cards[0]
    assert_cards(result, [(d(1), 0, 0, 0)])
    assert card.plan_equals_fact_applied is True
    assert_mgmt(result, {d(1): ""})
    assert_bank(result, closed=0)
    pef_records = [r for r in result.trace if r.code == PLAN_EQUALS_FACT]
    assert len(pef_records) == 1
    assert pef_records[0].step == "cards"
    assert dict(pef_records[0].data) == {"day": d(1), "plan_before": 720, "plan_after": 0,
                                         "policy": "yes"}
    assert_no_flags(flags)                     # LATE(None) подавлен


def test_ex_13_control_1_same_day_with_marks():
    prd = period(d(1), d(1))
    result = run_settle(prd, [day(1, "Я 12")], [IN(1, 8), OUT(1, 20)], st=settings([pef("yes", 1)]))
    assert_cards(result, [(d(1), 12, 12, 0)])
    assert result.cards[0].plan_equals_fact_applied is False
    assert_mgmt(result, {d(1): ""})
    assert not [r for r in result.trace if r.code == PLAN_EQUALS_FACT]


def test_ex_13_control_2_midnight_inside_carried_session():
    prd = period(d(1), d(2))
    marks = [IN(1, 22), OUT(2, 2)]
    result = run_settle(prd, [day(1, "Я 12"), day(2, "Я 12")], marks,
                        st=settings([pef("yes", 2)]))
    card2 = result.cards[1]
    assert card2.full_fact_minutes > 0
    assert card2.plan_equals_fact_applied is False
    assert card2.plan_minutes == 720


def test_ex_13_control_3_session_exactly_from_midnight():
    prd = OCT1_2
    rows = [day(1, "В"), day(2, "К 12")]
    st = settings([pef(PEF_AUTO_, 2)])
    result = run_settle(prd, rows, [IN(1, 23, 40)], st=st, mode="view",
                        now=at(3, 0))
    assert_cards(result, [(d(1), 0, 0, 0), (d(2), 12, 12, 0)])
    assert_mgmt(result, {d(1): "", d(2): "ДН 8, ДЯ 4"})
    assert result.cards[1].plan_equals_fact_applied is False
    assert not [r for r in result.trace if r.code == PLAN_EQUALS_FACT]


def test_ex_13_variant_k_auto_by_day_code_column():
    prd = period(d(1), d(1))
    st = settings([pef(PEF_AUTO_, 1)])
    result = run_settle(prd, [day(1, "К 12")], [], st=st)
    assert_cards(result, [(d(1), 0, 0, 0)])
    assert result.cards[0].plan_equals_fact_applied is True
    pef_records = [r for r in result.trace if r.code == PLAN_EQUALS_FACT]
    assert pef_records[0].data["policy"] == "auto_code"


def test_ex_13_variant_group_change_per_day():
    prd = OCT1_2
    rows = [day(1, "В", group="Смена 1"), day(2, "В", group="Пятидневка")]
    entry = double(period_=prd, group="Пятидневка")
    marks = [IN(1, 20), OUT(1, 23), IN(2, 20), OUT(2, 23)]
    result = run_settle(prd, rows, marks, st=settings([entry]), now=at(3, 0))
    assert_cards(result, [(d(1), 0, 0, 0), (d(2), 0, 0, 0)])
    assert_mgmt(result, {d(1): "ДЯ 2, ДН 1", d(2): "ДЯ2 2, ДН2 1"})
    assert_bank(result, closed=0)


def test_ex_13_variant_chk_defaults_missing_global():
    from app.engine.domain.settings.types import GlobalDefaults
    from app.engine.domain.settings.validate import validate_settings
    st = settings(global_defaults=GlobalDefaults(double_overtime=False, pays_overtime=True,
                                                 plan_equals_fact=None))
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    assert any(code == "CHK-DEFAULTS" for code, _ in exc.value.violations)


# ── EX-14 · Непрерывное присутствие через границу периодов ────────────────────

_PERIOD_A = period(dt.date(Y, 10, 30), dt.date(Y, 10, 31))
_PERIOD_B = period(dt.date(Y, 11, 1), dt.date(Y, 11, 2))


def _rows_a():
    return [day(30, "Я 12"), day(31, "Я 12")]


def _rows_b():
    return [day(1, "Я 12", month=11), day(2, "Я 12", month=11)]


def test_ex_14_run_a_period_border():
    marks = [Mark_(30, 8, "in", 10)]
    result = run_settle(_PERIOD_A, _rows_a(), marks, now=at(1, 0, month=11))
    assert_cards(result, [(dt.date(Y, 10, 30), 12, 12, 0), (dt.date(Y, 10, 31), 12, 12, 0)])
    assert_mgmt(result, {dt.date(Y, 10, 30): "ДЯ 2, ДН 2", dt.date(Y, 10, 31): "ДН 8, ДЯ 4"})
    assert_bank(result, closed=0)
    assert_deferred(result, [])


def Mark_(n, hh, kind, month):
    return (IN if kind == "in" else OUT)(n, hh, month=month)


def test_ex_14_run_b_session_restored_via_opening_mark():
    opening = Mark_(30, 8, "in", 10)
    marks = [Mark_(2, 20, "out", 11)]
    result = run_settle(_PERIOD_B, _rows_b(), marks, opening=opening,
                        now=at(3, 0, month=11))
    assert_cards(result, [(dt.date(Y, 11, 1), 12, 12, 0), (dt.date(Y, 11, 2), 12, 12, 0)])
    assert_mgmt(result, {dt.date(Y, 11, 1): "ДН 8, ДЯ 4", dt.date(Y, 11, 2): "ДН 6, ДЯ 2"})
    assert_bank(result, closed=0)


def test_ex_14_control_duration_conserved():
    """Σ полного факта по обоим прогонам = 84 ч — физической длительности сессии."""
    a = run_settle(_PERIOD_A, _rows_a(), [Mark_(30, 8, "in", 10)], now=at(1, 0, month=11))
    b = run_settle(_PERIOD_B, _rows_b(), [Mark_(2, 20, "out", 11)],
                   opening=Mark_(30, 8, "in", 10), now=at(3, 0, month=11))
    total = sum(c.full_fact_minutes for c in a.cards) + sum(c.full_fact_minutes for c in b.cards)
    assert total == 84 * 60


def test_ex_14_control_2_invalid_sequence_raises():
    marks = [Mark_(30, 8, "in", 10), Mark_(30, 12, "in", 10), Mark_(31, 20, "out", 10)]
    with pytest.raises(InvalidInputDataError) as exc:
        run_settle(_PERIOD_A, _rows_a(), marks, now=at(1, 0, month=11))
    assert exc.value.code == "CHK-PUNCH-SEQUENCE"


def test_ex_14_control_3_opening_out_ignored():
    """opening_mark = «ушёл» игнорируется (v7/R32): ровно одна сессия [30.10 08:00, 31.10 12:00).

    31.10, кусок [00:00, 12:00): рабочее 4 (в окне 08:00–20:00 лежит только
    [08:00, 12:00)), недостача 8, переработка ДН 6/ДЯ 2; каскад (CFG-CASCADE) гасит
    недостачу переработкой: ДЯ 2 (30.10), ДЯ 2 (31.10), ДН 2 (30.10), ДН 2 из 6
    (31.10) → коды УТ: 30.10 пуст, 31.10 «ДН 4»; cuts — четыре отрезка по 2 ч.
    Пример в спецификации исправлен по нормативной модели (правка v7.1/F-20,
    подтверждение владельца 11.10.2026, А.11).
    """
    from app.engine.domain.sessions.pair_marks import pair_marks
    from app.engine.domain.settings.defaults import default_settings
    from app.engine.domain.time.to_calc_mark import to_calc_mark

    st = default_settings()
    opening = Mark_(29, 7, "out", 10)
    marks = [Mark_(30, 8, "in", 10), Mark_(31, 12, "out", 10)]
    calc = [to_calc_mark(m, st) for m in marks]
    sessions = pair_marks(calc, to_calc_mark(opening, st))
    assert len(sessions) == 1
    assert sessions[0].start == at(30, 8)
    assert sessions[0].end == at(31, 12)

    result = run_settle(_PERIOD_A, _rows_a(), marks, opening=opening, now=at(1, 0, month=11))
    assert_cards(result, [(dt.date(Y, 10, 30), 12, 12, 0), (dt.date(Y, 10, 31), 12, 4, 8)])
    assert_mgmt(result, {dt.date(Y, 10, 30): "", dt.date(Y, 10, 31): "ДН 4"})
    assert_bank(result, closed=0, total_debt=8, paid=0, residual=0)
    assert result.deferred_blocks == ()
    assert_cuts(result, [(dt.date(Y, 10, 30), dt.date(Y, 10, 30), "ДЯ", 120, 120),
                         (dt.date(Y, 10, 31), dt.date(Y, 10, 31), "ДЯ", 120, 120),
                         (dt.date(Y, 10, 30), dt.date(Y, 10, 30), "ДН", 120, 120),
                         (dt.date(Y, 10, 31), dt.date(Y, 10, 31), "ДН", 120, 120)])


# ── EX-15 · Новое значение Табеля = строки настроек ───────────────────────────

WINDOWS_1075 = None


def _settings_1075():
    from app.engine.domain.settings.defaults import default_settings
    windows = dict(default_settings().windows)
    windows["Я 10,75"] = Window(8 * 60, 20 * 60)
    return settings(windows=windows)


def test_ex_15_new_timesheet_value_is_settings_row():
    prd = period(d(1), d(1))
    result = run_settle(prd, [day(1, "Я 10,75")], [IN(1, 8), OUT(1, 20)], st=_settings_1075())
    card = result.cards[0]
    assert card.timesheet_value == "Я 10,75"
    assert_cards(result, [(d(1), 12, 12, 0)])          # план карточки = окно (v7.1/R34)
    assert card.full_fact_minutes == 720
    assert_mgmt(result, {d(1): ""})
    assert_bank(result, closed=0)


def test_ex_15_control_left_later():
    prd = period(d(1), d(1))
    result = run_settle(prd, [day(1, "Я 10,75")], [IN(1, 8), OUT(1, 21)], st=_settings_1075())
    assert_cards(result, [(d(1), 12, 12, 0)])
    assert result.cards[0].full_fact_minutes == 780
    assert_mgmt(result, {d(1): "ДЯ 1"})
