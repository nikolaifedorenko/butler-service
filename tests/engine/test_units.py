"""Юнит-тесты функций каталога 8.1: границы из base 13 п.3, ядро pair_marks (R31/R32),
единый предикат «План=Факт» (R30), флаги, доска, нормализация, аккумулятор Codes."""
from __future__ import annotations

import datetime as dt

import pytest

from app.engine.domain.bank.close_bank import close_bank
from app.engine.domain.bank.granules_that_fit import granules_that_fit
from app.engine.domain.bank.minutes_to_cut import minutes_to_cut
from app.engine.domain.bank.pay_with_bank import pay_debt_with_bank
from app.engine.domain.board.assemble_board import assemble_board
from app.engine.domain.board.expected_arrivals import expected_arrivals
from app.engine.domain.board.expected_now import expected_now
from app.engine.domain.board.open_sessions import open_sessions
from app.engine.domain.day_card.apply_plan_equals_fact import apply_plan_equals_fact
from app.engine.domain.day_card.category_of import category_of
from app.engine.domain.day_card.codes_of_day import codes_of_day
from app.engine.domain.day_card.cut_working_time import cut_working_time
from app.engine.domain.day_card.debt_of_day import debt_of_day
from app.engine.domain.day_card.fmt_hours import fmt_hours
from app.engine.domain.day_card.has_presence_event import has_presence_event
from app.engine.domain.day_card.overtime_parts import overtime_parts
from app.engine.domain.day_card.plan_of_day import plan_of_day
from app.engine.domain.day_card.resolve_plan_equals_fact import resolve_plan_equals_fact
from app.engine.domain.day_card.split_by_category import split_by_category
from app.engine.domain.day_card.value_of import value_of
from app.engine.domain.day_card.window_of_day import window_of_day
from app.engine.domain.flags.drop_suppressed_lates import drop_suppressed_lates
from app.engine.domain.flags.early import early_flag
from app.engine.domain.flags.late import late_flag
from app.engine.domain.flags.off_shift import off_shift_flag
from app.engine.domain.flags.present_at import present_at
from app.engine.domain.opening.normalize_bank import normalize_opening_bank
from app.engine.domain.opening.normalize_deferred import normalize_deferred
from app.engine.domain.opening.round_signed import round_signed
from app.engine.domain.placement.codes import Codes
from app.engine.domain.placement.free_capacity import free_capacity
from app.engine.domain.presence.presence_intervals import presence_intervals
from app.engine.domain.presence.raw_presence_intervals import raw_presence_intervals
from app.engine.domain.presence.split_by_day import split_by_day
from app.engine.domain.schedule.expected_subintervals import expected_subintervals
from app.engine.domain.schedule.merge_absences import merge_absences
from app.engine.domain.schedule.shift_segments import merge_spans, shift_segments
from app.engine.domain.sessions.pair_marks import pair_marks
from app.engine.domain.settings.defaults import default_settings
from app.engine.domain.settings.resolve_modifier import resolve_modifier
from app.engine.domain.settings.types import (
    MOD_COUNTS_IN_UT,
    MOD_DOUBLE,
    ModifierEntry,
    Window,
)
from app.engine.domain.time.calc_horizon import calc_horizon
from app.engine.domain.time.calc_now import calc_now
from app.engine.domain.time.local_minute import local_minute
from app.engine.domain.time.period_days import period_days
from app.engine.domain.time.round_moment import round_moment
from app.engine.domain.time.to_calc_mark import to_calc_mark
from app.engine.domain.time.today_of import today_of
from app.engine.domain.types.entities import (
    Absence,
    Day,
    DeferredBlock,
    Interval,
    Mark,
    Period,
    RawInterval,
    Session,
    Shift,
)
from app.engine.domain.types.errors import InvalidInputDataError

from .helpers import IN, OUT, PEF_AUTO_, PEF_YES_, at, d, day, pef, settings

ST = default_settings()
EMP = "e1"


# ── время: round_moment / calc_now / calc_horizon / local_minute / today_of ───

def test_round_moment_exact_half_goes_forward():
    assert round_moment(at(1, 8, 30), ST) == at(1, 9)
    assert round_moment(at(1, 8, 29), ST) == at(1, 8)
    assert round_moment(at(1, 8, 31), ST) == at(1, 9)


def test_round_moment_on_grid_unchanged():
    assert round_moment(at(1, 8), ST) == at(1, 8)


def test_round_moment_2335_goes_to_next_midnight():
    assert round_moment(at(1, 23, 35), ST) == at(2, 0)


def test_round_moment_step_15():
    st = settings(step_minutes=15)
    assert round_moment(at(1, 8, 7, 30), st) == at(1, 8, 15)     # ровно половина — вверх
    assert round_moment(at(1, 8, 7, 29), st) == at(1, 8)


def test_round_moment_result_utc_aware():
    r = round_moment(at(1, 8, 30), ST)
    assert r.tzinfo is not None
    assert r == r.astimezone(dt.timezone.utc)


def test_calc_now_same_rule():
    assert calc_now(at(1, 23, 40), ST) == at(2, 0)


def test_calc_horizon_min_of_now_and_period_end():
    prd = Period(d(1), d(2))
    assert calc_horizon(prd, at(2, 15), ST) == at(2, 15)
    assert calc_horizon(prd, at(5, 0), ST) == at(3, 0)          # полночь после period.end


def test_calc_horizon_never_beyond_period_when_now_rounded_to_midnight():
    prd = Period(d(1), d(1))
    # now_calc округлился до следующей полуночи — H не выходит за конец периода (EX-39)
    assert calc_horizon(prd, at(2, 0), ST) == at(2, 0)


def test_local_minute_bounds():
    assert local_minute(at(1, 0), d(1), ST) == 0
    assert local_minute(at(1, 23, 59), d(1), ST) == 1439
    assert local_minute(at(2, 0), d(1), ST) == 1440


def test_today_of_uses_raw_now():
    assert today_of(at(1, 23, 40), ST) == d(1)
    assert today_of(at(2, 0), ST) == d(2)


def test_to_calc_mark_keeps_source():
    m = IN(1, 8, 30)
    cm = to_calc_mark(m, ST)
    assert cm.source is m
    assert cm.at_calc == at(1, 9)


def test_period_days_inclusive():
    assert period_days(Period(d(1), d(3))) == (d(1), d(2), d(3))
    assert period_days(Period(d(1), d(1))) == (d(1),)


# ── Табель и настройки: value_of / fmt_hours / window / plan ─────────────────

def test_fmt_hours_integers_and_fractions():
    assert fmt_hours(720) == "12"
    assert fmt_hours(510) == "8,5"
    assert fmt_hours(495) == "8,25"
    assert fmt_hours(645) == "10,75"
    assert fmt_hours(15) == "0,25"


def test_value_of_with_and_without_hours():
    assert value_of(day(1, "Я 12"), ST) == "Я 12"
    assert value_of(day(1, "Я 10,75"), ST) == "Я 10,75"
    assert value_of(day(1, "В"), ST) == "В"
    assert value_of(day(1, "ОТ"), ST) == "ОТ"


def test_window_of_day_none_for_value_without_hours():
    assert window_of_day(day(1, "В"), ST) is None
    assert window_of_day(day(1, "Я 12"), ST) == Window(480, 1200)


def test_plan_of_day_is_window_length_not_row_plan():
    st = settings(windows={**dict(ST.windows), "Я 10,75": Window(480, 1200)})
    assert plan_of_day(day(1, "Я 10,75"), st) == 720      # R34: план карточки = окно
    assert plan_of_day(day(1, "В"), st) == 0


# ── модификаторы: приоритеты 1–7, группа по дням ──────────────────────────────

def test_resolve_modifier_priority_levels():
    prd = Period(d(1), d(5))
    entries = [
        ModifierEntry(MOD_DOUBLE, False, employee_id=EMP, day=d(1)),            # 1
        ModifierEntry(MOD_DOUBLE, True, employee_id=EMP, period=prd),           # 2
        ModifierEntry(MOD_DOUBLE, False, group="Смена 1", day=d(1)),            # 3
        ModifierEntry(MOD_DOUBLE, True, group="Смена 1", period=prd),           # 4
    ]
    st = settings(entries)
    row1 = Day(d(1), "В", 0, EMP, "Смена 1")
    row3 = Day(d(3), "В", 0, EMP, "Смена 1")
    assert resolve_modifier(MOD_DOUBLE, row1, st) is False   # уровень 1 сильнее всех
    assert resolve_modifier(MOD_DOUBLE, row3, st) is True    # уровень 2
    other = Day(d(3), "В", 0, "e2", "Пятидневка")
    assert resolve_modifier(MOD_DOUBLE, other, st) is False  # глобальный дефолт


def test_resolve_modifier_group_per_day():
    entry = ModifierEntry(MOD_DOUBLE, True, group="Пятидневка", period=Period(d(1), d(2)))
    st = settings([entry])
    row1 = Day(d(1), "В", 0, EMP, "Смена 1")
    row2 = Day(d(2), "В", 0, EMP, "Пятидневка")
    assert resolve_modifier(MOD_DOUBLE, row1, st) is False
    assert resolve_modifier(MOD_DOUBLE, row2, st) is True


def test_resolve_counts_in_ut_level7_is_day_code_column():
    assert resolve_modifier(MOD_COUNTS_IN_UT, day(1, "В"), ST) is True
    assert resolve_modifier(MOD_COUNTS_IN_UT, day(1, "Б"), ST) is False


def test_resolve_plan_equals_fact_explicit_yes_policy():
    st = settings([pef(PEF_YES_, 1)])
    assert resolve_plan_equals_fact(day(1, "Я 12"), st) == (True, "yes")
    # явное «Да» даёт policy=yes даже для кода с Авто-колонкой (К)
    assert resolve_plan_equals_fact(day(1, "К 12"), st) == (True, "yes")


def test_resolve_plan_equals_fact_auto_only_by_code_column():
    st = settings([pef(PEF_AUTO_, 1)])
    assert resolve_plan_equals_fact(day(1, "К 12"), st) == (True, "auto_code")
    assert resolve_plan_equals_fact(day(1, "Я 12"), st) == (False, None)


# ── единый предикат «План=Факт» (R30): по тесту на каждое условие ─────────────

def _pef_apply(row, fact, has_event, st=None):
    st = st or settings([pef(PEF_YES_, row.day.day)])
    plan = plan_of_day(row, st)
    return apply_plan_equals_fact(row, fact, plan, has_event, st)


def test_pef_condition_1_code_without_hours_not_applied():
    row = day(1, "В")
    plan, applied = _pef_apply(row, fact=0, has_event=False)
    assert (plan, applied) == (0, False)


def test_pef_condition_2_modifier_no_not_applied():
    row = day(1, "Я 12")
    plan, applied = _pef_apply(row, 0, False, st=ST)        # глобальный дефолт «Нет»
    assert (plan, applied) == (720, False)


def test_pef_condition_3_event_without_fact_not_applied():
    row = day(1, "Я 12")
    plan, applied = _pef_apply(row, fact=0, has_event=True)
    assert (plan, applied) == (720, False)


def test_pef_condition_4_fact_without_event_not_applied():
    row = day(1, "Я 12")
    plan, applied = _pef_apply(row, fact=60, has_event=False)
    assert (plan, applied) == (720, False)


def test_pef_all_conditions_applied_zeroes_plan():
    row = day(1, "Я 12")
    plan, applied = _pef_apply(row, fact=0, has_event=False)
    assert (plan, applied) == (0, True)


def test_pef_window_and_schedule_do_not_participate():
    """Окно, отличное от плана, и согласованное отсутствие, накрывающее день,
    на предикат не влияют (CFG-MODIFIERS «Что в предикате не участвует», 12.23)."""
    st = settings([pef(PEF_YES_, 1)], windows={**dict(ST.windows), "Я 10,75": Window(480, 1200)})
    row = Day(d(1), "Я", 645, EMP, "Смена 1")
    plan, applied = _pef_apply(row, fact=0, has_event=False, st=st)
    assert (plan, applied) == (0, True)      # отсутствие/окно не блокируют применение


# ── has_presence_event: событие против факта (EX-48, EX-50) ──────────────────

def test_has_presence_event_true_for_marks_in_day():
    assert has_presence_event(day(1, "К 12"), [IN(1, 8, 10), OUT(1, 8, 20)], ST) is True


def test_has_presence_event_false_without_day_marks():
    assert has_presence_event(day(1, "К 12"), [IN(2, 0)], ST) is False


def test_has_presence_event_boundary_midnight_belongs_to_new_day():
    assert has_presence_event(day(1, "В"), [IN(2, 0)], ST) is False
    assert has_presence_event(day(2, "В"), [IN(2, 0)], ST) is True


# ── ядро pair_marks (R31/R32) ─────────────────────────────────────────────────

def test_pair_marks_basic_alternation():
    sessions = pair_marks([IN(1, 8), OUT(1, 20), IN(2, 9), OUT(2, 18)])
    assert sessions == (Session(at(1, 8), at(1, 20)), Session(at(2, 9), at(2, 18)))


def test_pair_marks_opening_in_starts_first_session():
    sessions = pair_marks([OUT(2, 8)], opening_mark=IN(1, 20))
    assert sessions == (Session(at(1, 20), at(2, 8)),)


def test_pair_marks_opening_out_ignored():
    sessions = pair_marks([IN(1, 8), OUT(1, 12)], opening_mark=OUT(1, 7))
    assert sessions == (Session(at(1, 8), at(1, 12)),)


def test_pair_marks_closing_out_closes_tail():
    sessions = pair_marks([IN(1, 8)], closing_mark=OUT(1, 20))
    assert sessions == (Session(at(1, 8), at(1, 20)),)


def test_pair_marks_closing_in_ignored_session_stays_open():
    sessions = pair_marks([IN(1, 8)], closing_mark=IN(1, 9))
    assert sessions == (Session(at(1, 8), None),)


def test_pair_marks_empty_selection_with_opening_in():
    sessions = pair_marks([], opening_mark=IN(1, 8), horizon=at(1, 20))
    assert sessions == (Session(at(1, 8), at(1, 20)),)


def test_pair_marks_empty_selection_without_opening():
    assert pair_marks([]) == ()


def test_pair_marks_open_session_clipped_by_horizon():
    sessions = pair_marks([IN(1, 8)], horizon=at(1, 12))
    assert sessions == (Session(at(1, 8), at(1, 12)),)


def test_pair_marks_session_beyond_horizon_dropped():
    sessions = pair_marks([IN(1, 8), OUT(2, 20)], horizon=at(1, 12))
    assert sessions == (Session(at(1, 8), at(1, 12)),)


def test_pair_marks_in_at_open_session_raises():
    with pytest.raises(InvalidInputDataError) as exc:
        pair_marks([IN(1, 8), IN(1, 12), OUT(1, 20)])
    assert exc.value.code == "CHK-PUNCH-SEQUENCE"
    assert exc.value.data["index"] == 1


def test_pair_marks_out_first_raises():
    with pytest.raises(InvalidInputDataError) as exc:
        pair_marks([OUT(1, 8), IN(1, 12)])
    assert exc.value.code == "CHK-PUNCH-SEQUENCE"
    assert exc.value.data["index"] == 0


def test_pair_marks_no_repaired_result_on_violation():
    """При недопустимой последовательности нет «починенного» результата (12.22)."""
    with pytest.raises(InvalidInputDataError):
        pair_marks([IN(1, 8), IN(1, 9)])


def test_pair_marks_works_with_calc_marks():
    calc = [to_calc_mark(m, ST) for m in (IN(1, 8, 30), OUT(1, 20, 10))]
    sessions = pair_marks(calc)
    assert sessions == (Session(at(1, 9), at(1, 20)),)


def test_pair_marks_zero_length_session_kept():
    sessions = pair_marks([IN(1, 8), OUT(1, 8)])
    assert sessions == (Session(at(1, 8), at(1, 8)),)


# ── split_by_day / presence_intervals / raw_presence_intervals ───────────────

def test_split_by_day_over_midnight():
    from .helpers import TZ
    sessions = (Session(at(1, 20), at(3, 8)),)
    pieces = split_by_day(sessions, Period(d(1), d(3)), ST)
    local = lambda m: m.astimezone(TZ).strftime("%H:%M")  # noqa: E731
    assert [(str(day_), local(s), local(e)) for day_, s, e in pieces] == [
        ("2026-10-01", "20:00", "00:00"), ("2026-10-02", "00:00", "00:00"),
        ("2026-10-03", "00:00", "08:00")]


def test_split_by_day_out_exactly_at_midnight_gives_zero_piece_dropped():
    sessions = (Session(at(1, 20), at(2, 0)),)
    pieces = split_by_day(sessions, Period(d(1), d(2)), ST)
    assert [p[0] for p in pieces] == [d(1)]


def test_split_by_day_pieces_outside_period_dropped():
    sessions = (Session(at(1, 20), at(3, 8)),)
    pieces = split_by_day(sessions, Period(d(2), d(2)), ST)
    assert [p[0] for p in pieces] == [d(2)]


def test_presence_intervals_on_grid():
    prd = Period(d(1), d(1))
    calc = [to_calc_mark(m, ST) for m in (IN(1, 8, 30), OUT(1, 20, 10))]
    iv = presence_intervals(prd, calc, None, at(2, 0), ST)
    assert iv == {d(1): (Interval(d(1), 540, 1200),)}


def test_raw_presence_intervals_keep_seconds():
    prd = Period(d(1), d(1))
    marks = [Mark(EMP, at(1, 8, 5, 1), "in"), Mark(EMP, at(1, 20, 0, 30), "out")]
    iv = raw_presence_intervals(prd, marks, None, at(1, 23), ST)
    assert iv[d(1)][0].start_utc == at(1, 8, 5, 1)
    assert iv[d(1)][0].end_utc == at(1, 20, 0, 30)


def test_raw_presence_open_interval_ends_at_now():
    prd = Period(d(1), d(1))
    iv = raw_presence_intervals(prd, [IN(1, 8)], None, at(1, 12, 30, 45), ST)
    assert iv[d(1)][0].end_utc == at(1, 12, 30, 45)


# ── карточка дня: категории, рабочее, переработка, недостача ─────────────────

def test_category_of_boundaries():
    assert category_of(0, ST) == "ДН"
    assert category_of(359, ST) == "ДН"
    assert category_of(360, ST) == "ДЯ"
    assert category_of(1319, ST) == "ДЯ"
    assert category_of(1320, ST) == "ДН"
    assert category_of(1439, ST) == "ДН"


def test_split_by_category_crossing_midnight():
    iv = Interval(d(1), 22 * 60, 24 * 60)
    assert dict(split_by_category(iv, ST)) == {"ДН": 120}
    iv2 = Interval(d(1), 0, 8 * 60)
    assert dict(split_by_category(iv2, ST)) == {"ДН": 360, "ДЯ": 120}


def test_cut_working_time_none_window_zero():
    ivs = (Interval(d(1), 480, 1200),)
    assert cut_working_time(ivs, None) == 0
    assert cut_working_time(ivs, Window(480, 1200)) == 720


def test_overtime_parts_outside_window():
    ivs = (Interval(d(1), 420, 1260),)
    parts = overtime_parts(ivs, Window(480, 1200))
    assert [(p.start_minute, p.end_minute) for p in parts] == [(420, 480), (1200, 1260)]
    assert overtime_parts(ivs, None) == ivs


def test_debt_of_day_from_window_and_applied():
    row = day(1, "Я 12")
    assert debt_of_day(row, 660, False, ST) == 60
    assert debt_of_day(row, 660, True, ST) == 0
    assert debt_of_day(row, 720, False, ST) == 0
    assert debt_of_day(day(1, "В"), 0, False, ST) == 0     # нет окна → 0


def test_codes_of_day_weight_suffix():
    parts = (Interval(d(1), 1320, 1440),)
    assert dict(codes_of_day(day(1, "В"), parts, ST)) == {"ДН": 120}
    st = settings([ModifierEntry(MOD_DOUBLE, True, day=d(1))])
    assert dict(codes_of_day(day(1, "В"), parts, st)) == {"ДН2": 120}


# ── аккумулятор Codes ─────────────────────────────────────────────────────────

def test_codes_add_take_place_get():
    codes = Codes()
    codes.add(d(1), "ДЯ", 240, None)
    assert codes.get(d(1), "ДЯ", None) == 240
    codes.place(d(1), "ДЯ", d(2), 120)
    assert codes.get(d(1), "ДЯ", None) == 120
    assert codes.get(d(1), "ДЯ", d(2)) == 120
    assert codes.placed_total(d(2)) == 120
    codes.take(d(1), "ДЯ", None, 120)
    assert codes.get(d(1), "ДЯ", None) == 0
    blocks = codes.blocks()
    assert len(blocks) == 1
    assert (blocks[0].source_day, blocks[0].tariff, blocks[0].placed_day,
            blocks[0].minutes) == (d(1), "ДЯ", d(2), 120)


def test_codes_take_only_positive():
    codes = Codes()
    codes.add(d(1), "ДЯ", 60, None)
    with pytest.raises(ValueError):
        codes.take(d(1), "ДЯ", None, 0)
    with pytest.raises(ValueError):
        codes.take(d(1), "ДЯ", None, 120)


def test_free_capacity_from_window_with_plan_equals_fact_day():
    from app.engine.domain.types.results import DayCard
    card = DayCard(day=d(2), timesheet_value="К 12", plan_minutes=0, full_fact_minutes=0,
                   work_minutes=0, overtime_minutes=0, debt_minutes=0, codes={},
                   pays_overtime=True, plan_equals_fact_applied=True)
    codes = Codes()
    assert free_capacity(card, codes, ST) == 1440 - 720     # ёмкость от окна, не от плана 0


def test_free_capacity_no_window():
    from app.engine.domain.types.results import DayCard
    card = DayCard(day=d(1), timesheet_value="В", plan_minutes=0, full_fact_minutes=0,
                   work_minutes=0, overtime_minutes=0, debt_minutes=0, codes={},
                   pays_overtime=True, plan_equals_fact_applied=False)
    assert free_capacity(card, Codes(), ST) == 1440


# ── нормализация входящих остатков (4.6) ──────────────────────────────────────

def test_round_signed_half_away_from_zero():
    assert round_signed(30, 60) == 60
    assert round_signed(-30, 60) == -60
    assert round_signed(15, 60) == 0
    assert round_signed(-15, 60) == 0
    assert round_signed(45, 60) == 60
    assert round_signed(-45, 60) == -60


def test_normalize_opening_bank_records():
    value, records = normalize_opening_bank(45, 15, 60)
    assert value == 60
    assert len(records) == 1
    assert records[0].data["kind"] == "bank"


def test_normalize_opening_bank_same_step_no_records():
    value, records = normalize_opening_bank(45, 60, 60)
    assert (value, records) == (45, ())


def test_normalize_opening_bank_already_on_grid_no_record():
    value, records = normalize_opening_bank(120, 15, 60)
    assert (value, records) == (120, ())


def test_normalize_deferred_each_block_separately_zero_excluded_record_kept():
    blocks = [DeferredBlock(d(1), "ДЯ", 15), DeferredBlock(d(1), "ДН", 75)]
    out, records = normalize_deferred(blocks, 15, 60)
    assert out == (DeferredBlock(d(1), "ДН", 60),)
    assert len(records) == 2


def test_normalize_deferred_same_step():
    blocks = [DeferredBlock(d(1), "ДЯ", 45)]
    out, records = normalize_deferred(blocks, 60, 60)
    assert out == tuple(blocks)
    assert records == ()


# ── банк и каскад ─────────────────────────────────────────────────────────────

def test_pay_debt_with_bank():
    assert pay_debt_with_bank(120, 300) == (120, 0, 180)
    assert pay_debt_with_bank(300, 120) == (120, 180, 0)
    assert pay_debt_with_bank(120, -60) == (0, 120, 0)


def test_granules_and_minutes_to_cut():
    assert granules_that_fit(120, 2, 60) == 1
    assert minutes_to_cut(120, 2, 300, 60) == 60
    assert minutes_to_cut(60, 2, 300, 60) == 0        # гранула дороже остатка (EX-21)
    assert minutes_to_cut(600, 1, 120, 60) == 120     # ограничено available


def test_close_bank_can_be_negative():
    closed, records = close_bank(0, 60)
    assert closed == -60
    assert records[0].code == "RESIDUAL_CARRIED"
    closed, records = close_bank(120, 0)
    assert (closed, records) == (120, ())


# ── График: отрезки, слияния, подинтервалы ────────────────────────────────────

def test_shift_segments_over_midnight_and_merge_adjacent():
    shifts = [Shift(EMP, at(1, 20), at(2, 8)), Shift(EMP, at(2, 8), at(2, 20))]
    seg = shift_segments(shifts, ST)
    assert seg[d(1)] == ((at(1, 20), at(2, 0)),)
    assert seg[d(2)] == ((at(2, 0), at(2, 20)),)     # смежные сливаются (R17)


def test_merge_spans_overlapping():
    assert merge_spans([(at(1, 8), at(1, 12)), (at(1, 11), at(1, 14))]) == \
        ((at(1, 8), at(1, 14)),)


def test_merge_absences_over_midnight():
    merged = merge_absences([Absence(EMP, at(1, 23), at(2, 3))])
    assert merged == ((at(1, 23), at(2, 3)),)


def test_expected_subintervals_exact_boundaries():
    segs = ((at(1, 8), at(1, 20)),)
    # отсутствие точно по границам подинтервала → подинтервалов нет
    assert expected_subintervals(segs, ((at(1, 8), at(1, 20)),), d(1)) == ()
    # отсутствие в середине → два подинтервала
    assert expected_subintervals(segs, ((at(1, 12), at(1, 15)),), d(1)) == \
        ((at(1, 8), at(1, 12)), (at(1, 15), at(1, 20)))
    # отсутствие вне отрезка → без изменений
    assert expected_subintervals(segs, ((at(1, 21), at(1, 22)),), d(1)) == segs


# ── флаги: границы present_at, LATE, EARLY, OFF_SHIFT, подавление ─────────────

def _raw(start, end, day_=None):
    return RawInterval(day_ or d(1), start, end)


def test_present_at_start_inclusive_end_exclusive():
    ivs = (_raw(at(1, 8), at(1, 20)),)
    assert present_at(ivs, at(1, 8)) is True        # приход ровно в start — присутствует
    assert present_at(ivs, at(1, 19, 59)) is True
    assert present_at(ivs, at(1, 20)) is False      # уход ровно в end — уже нет


def test_late_flag_arrival_exactly_at_start_no_flag():
    subs = ((at(1, 8), at(1, 20)),)
    ivs = (_raw(at(1, 8), at(1, 20)),)
    assert late_flag(subs, ivs, at(1, 23), ST) == ()


def test_late_flag_departure_exactly_at_start_of_other_shift_gives_none_actual():
    """R29: уход ровно в S.start другой смены → LATE(None)."""
    ivs = (_raw(at(1, 6), at(1, 8)),)               # сессия закончилась ровно в 08:00
    subs = ((at(1, 8), at(1, 20)),)
    flags = late_flag(subs, ivs, at(1, 23), ST)
    assert len(flags) == 1
    assert flags[0].data["actual_at"] is None       # интервалов, НАЧАВШИХСЯ в S, нет


def test_late_flag_within_limit_no_flag():
    subs = ((at(1, 8), at(1, 20)),)
    ivs = (_raw(at(1, 8, 5), at(1, 20)),)
    assert late_flag(subs, ivs, at(1, 23), ST) == ()


def test_late_flag_none_before_gate_not_set():
    subs = ((at(1, 8), at(1, 20)),)
    assert late_flag(subs, (), at(1, 8, 4), ST) == ()       # now < S.start + лимит


def test_early_flag_departure_exactly_at_end_no_flag():
    subs = ((at(1, 8), at(1, 20)),)
    ivs = (_raw(at(1, 8), at(1, 20)),)
    assert early_flag(subs, ivs, at(1, 23), ST) == ()


def test_early_flag_no_presence_no_flag():
    subs = ((at(1, 8), at(1, 20)),)
    assert early_flag(subs, (), at(1, 23), ST) == ()


def test_early_flag_set():
    subs = ((at(1, 8), at(1, 20)),)
    ivs = (_raw(at(1, 8), at(1, 19)),)
    flags = early_flag(subs, ivs, at(1, 23), ST)
    assert len(flags) == 1
    assert flags[0].data["expected_at"] == at(1, 20)
    assert flags[0].data["actual_at"] == at(1, 19)


def test_off_shift_flag_requires_no_subintervals_and_presence():
    row = day(1, "ОТ")
    ivs = (_raw(at(1, 8), at(1, 12)),)
    flag = off_shift_flag((), ivs, (), (), row)
    assert flag is not None
    assert flag.data["day_code"] == "ОТ"
    assert flag.data["first_presence_at"] == at(1, 8)
    assert off_shift_flag(((at(1, 8), at(1, 20)),), ivs, ((at(1, 8), at(1, 20)),), (), row) is None
    assert off_shift_flag((), (), (), (), row) is None


def test_drop_suppressed_lates_only_none_actual():
    from app.engine.domain.types.results import Flag
    late_none = Flag(d(1), "LATE", {"expected_at": at(1, 8), "actual_at": None})
    late_real = Flag(d(1), "LATE", {"expected_at": at(1, 8), "actual_at": at(1, 9)})
    assert drop_suppressed_lates([late_none, late_real], True) == (late_real,)
    assert drop_suppressed_lates([late_none], False) == (late_none,)


# ── доска (16.2) ──────────────────────────────────────────────────────────────

def _board_data(now):
    last_marks = [Mark("e1", at(1, 8), "in"), Mark("e2", at(1, 9), "out"),
                  Mark("e3", at(1, 7, 30), "in")]
    shifts = [Shift("e1", at(1, 8), at(1, 20)), Shift("e3", at(1, 12), at(1, 18)),
              Shift("e4", at(1, 10), at(1, 14))]
    absences = [Absence("e4", at(1, 10), at(1, 14))]
    return last_marks, shifts, absences


def test_open_sessions_only_last_in():
    last_marks, _, _ = _board_data(at(1, 9, 30))
    opened = open_sessions(last_marks, at(1, 9, 30))
    assert [(e, m) for e, m in opened] == [("e3", at(1, 7, 30)), ("e1", at(1, 8))]


def test_expected_now_counts_present_subinterval_start_inclusive():
    _, shifts, absences = _board_data(at(1, 9))
    # e1: [08:00,20:00) — в 08:00 уже ожидается; e3: [12:00,18:00) — ещё нет;
    # e4: смена полностью покрыта отсутствием — не ожидается
    assert expected_now(shifts, absences, at(1, 8), ST) == 1
    assert expected_now(shifts, absences, at(1, 12), ST) == 2
    assert expected_now(shifts, absences, at(1, 21), ST) == 0


def test_expected_arrivals_skips_finished_and_absent_covered():
    _, shifts, absences = _board_data(at(1, 9))
    arrivals = expected_arrivals(shifts, absences, {"e1"}, at(1, 9), ST)
    # e3: [12:00,18:00) ещё не начался → already_started False; e4 — покрыт отсутствием
    assert [(a.employee_id, a.already_started) for a in arrivals] == [("e3", False)]
    late = expected_arrivals(shifts, absences, {"e1"}, at(1, 13), ST)
    assert [(a.employee_id, a.already_started) for a in late] == [("e3", True)]
    # завершившиеся подинтервалы (S.end ≤ now) не входят (R20)
    assert expected_arrivals(shifts, absences, {"e1"}, at(1, 19), ST) == ()


def test_expected_arrivals_one_nearest_per_employee():
    shifts = [Shift("e1", at(1, 10), at(1, 12)), Shift("e1", at(1, 14), at(1, 16))]
    arrivals = expected_arrivals(shifts, [], set(), at(1, 9), ST)
    assert len(arrivals) == 1
    assert arrivals[0].expected_at_utc == at(1, 10)


def test_assemble_board_composition_and_minutes_open():
    last_marks, shifts, absences = _board_data(at(1, 9))
    board = assemble_board(last_marks, shifts, absences, at(1, 9, 30, 45), ST)
    assert board.at_work_now == 2
    assert board.expected_now == 1
    assert [(c.employee_id, c.minutes_open) for c in board.open_session_cards] == \
        [("e3", 120), ("e1", 90)]
    e3 = board.open_session_cards[0]
    assert e3.expected_today is True
    assert e3.shift_today == ((at(1, 12), at(1, 18)),)
    assert [(a.employee_id, a.expected_at_utc) for a in board.yet_to_come] == []


def test_assemble_board_determinism():
    last_marks, shifts, absences = _board_data(at(1, 9))
    b1 = assemble_board(last_marks, shifts, absences, at(1, 9), ST)
    b2 = assemble_board(list(reversed(last_marks)), list(reversed(shifts)),
                        list(reversed(absences)), at(1, 9), ST)
    assert b1 == b2


def test_board_open_session_minutes_open_grows_forgotten_out():
    last_marks = [Mark("e1", at(1, 8), "in")]
    board = assemble_board(last_marks, [], [], at(2, 8), ST)
    assert board.open_session_cards[0].minutes_open == 24 * 60
    assert board.open_session_cards[0].expected_today is False


# ── неизменяемость и сериализуемость результатов (13 п.13) ────────────────────

def test_result_collections_are_readonly():
    from .helpers import run_settle
    result = run_settle(Period(d(1), d(1)), [day(1, "Я 12")], [IN(1, 8), OUT(1, 20)])
    with pytest.raises(TypeError):
        result.mgmt_timesheet[d(1)] = {}
    with pytest.raises(TypeError):
        result.mgmt_timesheet[d(1)]["ДЯ"] = 60
    with pytest.raises(TypeError):
        result.cards[0].codes["ДЯ"] = 60


def test_reason_data_readonly():
    from app.engine.domain.types.results import Reason
    r = Reason("bank", "BANK_APPLIED", {"used": 60})
    with pytest.raises(TypeError):
        r.data["used"] = 0


def test_input_mutation_after_call_does_not_change_result():
    from .helpers import run_settle
    marks = [IN(1, 8), OUT(1, 20)]
    result = run_settle(Period(d(1), d(1)), [day(1, "Я 12")], marks)
    marks.append(IN(2, 8))
    assert result.cards[0].full_fact_minutes == 720
