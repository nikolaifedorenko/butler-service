"""Application-тесты (13 п.6, 15 п.16, 7.2): truth table четырёх режимов (v7/R33),
эффективный период и трудоустройство (R23/R35), EX-53, EX-55, EX-38 контроль,
гранулярность (R36), посев OPENING_SEED (R37), доска (R38), планы УТ (R39),
атомарность, история сессий (16.4), График (16.3) и Табель (16.5)."""
from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from app.engine.application import bank_adjustment, schedule_view, timesheet_edit, view_sessions
from app.engine.application.close_period import close_period
from app.engine.application.errors import (
    AdjustmentClosedPeriodError,
    PeriodAlreadyClosedError,
    PeriodNotClosedError,
    PeriodOutsideEmploymentError,
    PreviousPeriodNotClosedError,
    RecalculationForbiddenError,
    ScheduleDayNotEditableError,
    SeedNotAllowedError,
    TimesheetLockedError,
)
from app.engine.application.load_inputs import load_inputs
from app.engine.application.months import (
    close_month,
    half_month_period,
    is_first_period,
    month_period,
    next_period,
    period_containing,
    previous_period,
    recalculate_month,
)
from app.engine.application.period_view import day_views
from app.engine.application.presence_board import presence_board
from app.engine.application.recalculate import recalculate
from app.engine.application.view_period import view_period
from app.engine.domain.settings.types import GRANULARITY_HALF_MONTH
from app.engine.domain.types.entities import (
    Day,
    DeferredBlock,
    Employment,
    Mark,
    Period,
    Shift,
)
from app.engine.domain.types.errors import (
    IncompletePeriodError,
    IncompleteTimesheetError,
    InvalidInputDataError,
    UnknownDayCodeError,
    UnknownTimesheetValueError,
)

from .fakes import FakeDb, build_fakes
from .helpers import EMP, IN, OUT, TZ, at, d, day, settings

OCT = month_period(2026, 10)
SEP = month_period(2026, 9)
NOV = month_period(2026, 11)
ST_MS = settings()          # default_settings c tz Europe/Moscow


def _st():
    from app.engine.domain.settings.defaults import default_settings
    return default_settings()


# ── общий стенд: сотрудник, Табель октября, посев начального банка ────────────

def _stand(rows=None, marks=(), employment=None, seed=True, seed_period=None):
    db = FakeDb(settings=_st())
    db.timesheet_rows = list(rows if rows is not None else
                             [day(n, "Я 12") if n % 2 else day(n, "В") for n in range(1, 32)])
    db.marks = list(marks)
    db.employment[EMP] = employment or Employment(dt.date(2026, 10, 1), None)
    if seed:
        db.adjustments.append((EMP, (seed_period or OCT).start, 0, "OPENING_SEED"))
    db.active = [EMP]
    return build_fakes(db)


def _rows_full_month(value="В", month=10, first=1, last=None):
    import calendar
    last = last or calendar.monthrange(2026, month)[1]
    return [Day(dt.date(2026, month, n), value, 0, EMP, "Смена 1")
            for n in range(first, last + 1)]


# ── режим 1: view незакрытого периода (колонка таблицы 7.2) ───────────────────

def test_view_unclosed_calculates_and_saves_nothing():
    db, ports = _stand()
    view = view_period(EMP, OCT, at(15, 12), ports)
    assert len(view.settle.cards) == 31
    assert db.closings == {}
    assert db.deferred == {}
    assert "carry_over.save_deferred" not in db.queries
    assert "bank_write.save_closing_bank" not in db.queries
    assert "store.save_result" not in db.queries


def test_view_unclosed_rejected_when_previous_not_closed(monkeypatch):
    db, ports = _stand(seed=False)          # сентябрь не закрыт, посева нет
    calls = _spy_settle(monkeypatch)
    with pytest.raises(PreviousPeriodNotClosedError):
        view_period(EMP, OCT, at(15, 12), ports)
    assert calls["settle"] == 0             # домен не вызывается (RUL-VIEW-AFTER-PREVIOUS)


def test_view_allowed_with_opening_seed():
    db, ports = _stand(seed=True)           # первый период + посев → допускается
    view = view_period(EMP, OCT, at(15, 12), ports)
    assert view.settle.cards


def _spy_settle(monkeypatch):
    import app.engine.application._pipeline as pipeline
    calls = {"settle": 0}
    original = pipeline.settle

    def spy(*args, **kwargs):
        calls["settle"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "settle", spy)
    return calls


# ── режим 2: чтение закрытого периода — без домена ────────────────────────────

def test_view_closed_reads_store_without_domain(monkeypatch):
    db, ports = _stand()
    closed = close_period(EMP, OCT, at(1, 0, month=11), ports)
    calls = _spy_settle(monkeypatch)
    view = view_period(EMP, OCT, at(5, 0, month=12), ports)
    assert calls["settle"] == 0
    assert view.settle == closed.settle
    assert view.flags == closed.flags


# ── режим 3: close — атомарное сохранение всего (7.2–7.3) ─────────────────────

def test_close_saves_result_flags_bank_deferred_inputs_versions_state():
    db, ports = _stand()
    view = close_period(EMP, OCT, at(1, 0, month=11), ports)
    row = db.closings[(EMP, OCT.start)]
    assert row["result"] == view.settle
    assert row["flags"] == view.flags                    # снимок флагов сохранён
    assert row["inputs"].bank_open == 0
    assert row["versions"] == list(_st().versions)
    assert db.deferred.get((EMP, NOV.start)) is not None  # переносы во вход следующего
    assert ports.store.period_state(EMP, OCT).closed is True


def test_close_rejected_when_already_closed():
    db, ports = _stand()
    close_period(EMP, OCT, at(1, 0, month=11), ports)
    with pytest.raises(PeriodAlreadyClosedError):
        close_period(EMP, OCT, at(2, 0, month=11), ports)


def test_close_rejected_when_previous_not_closed_and_no_seed(monkeypatch):
    db, ports = _stand(seed=False)
    calls = _spy_settle(monkeypatch)
    with pytest.raises(PreviousPeriodNotClosedError):
        close_period(EMP, OCT, at(1, 0, month=11), ports)
    assert calls["settle"] == 0


def test_close_rejected_before_period_end(monkeypatch):
    db, ports = _stand()
    calls = _spy_settle(monkeypatch)
    with pytest.raises(IncompletePeriodError):
        close_period(EMP, OCT, at(31, 23, 40), ports)
    assert calls["settle"] == 0
    assert db.closings == {}


def test_close_atomic_failure_saves_nothing():
    db, ports = _stand()
    db.fail_on = "save_deferred"            # сбой между записями
    with pytest.raises(RuntimeError):
        close_period(EMP, OCT, at(1, 0, month=11), ports)
    assert db.closings == {}                # UnitOfWork откатил всё
    assert db.deferred == {}


# ── режим 4: recalculate (7.2, v7/R28) ────────────────────────────────────────

def test_recalculate_not_closed_raises():
    db, ports = _stand()
    with pytest.raises(PeriodNotClosedError):
        recalculate(EMP, OCT, at(1, 0, month=11), ports)


def test_recalculate_forbidden_when_next_closed():
    db, ports = _stand(rows=_rows_full_month() + _rows_full_month(month=11))
    close_period(EMP, OCT, at(1, 0, month=11), ports)
    close_period(EMP, NOV, at(1, 0, month=12), ports)
    with pytest.raises(RecalculationForbiddenError):
        recalculate(EMP, OCT, at(2, 0, month=12), ports)


def test_ex_53_recalculate_closed_period():
    """EX-53: исправление Табеля после закрытия → пересчёт размещает блок,
    исчезнувший перенос удаляется из входа следующего периода. P — октябрь, Q — ноябрь
    (короткие периоды примера — иллюстративные; механика идентична, преамбула 11)."""
    rows = [day(1, "ОТ")] + _rows_full_month("ДО", first=2)
    db, ports = _stand(rows=rows, marks=[IN(1, 8), OUT(1, 20)], seed=True)
    closed = close_period(EMP, OCT, at(1, 0, month=11), ports)
    assert closed.settle.deferred_blocks == (DeferredBlock(d(1), "ДЯ", 720),)
    assert [r.code for r in closed.settle.exceptions] == ["NO_RECEIVER"]
    assert db.deferred[(EMP, NOV.start)] == [DeferredBlock(d(1), "ДЯ", 720)]
    inputs_before = db.closings[(EMP, OCT.start)]["inputs"]

    # шаг 2: исправление Табеля — 02.10 должен быть «В»
    db.timesheet_rows = [day(1, "ОТ"), day(2, "В")] + _rows_full_month("ДО", first=3)
    recalculated = recalculate(EMP, OCT, at(5, 0, month=11), ports)

    assert dict(recalculated.settle.mgmt_timesheet[d(2)]) == {"ДЯ": 720}
    assert recalculated.settle.deferred_blocks == ()
    assert recalculated.settle.exceptions == ()
    # сохранение ЗАМЕНИЛО результат, банк, переносы и снимок флагов
    row = db.closings[(EMP, OCT.start)]
    assert row["result"] == recalculated.settle
    assert row["flags"] == recalculated.flags
    # исчезнувший перенос удалён из входа следующего периода
    assert db.deferred[(EMP, NOV.start)] == []
    # ClosingInputs заморожены — не перезаписаны
    assert row["inputs"] == inputs_before


def test_ex_53_control_recalculate_rereads_marks_fresh():
    """R28: отметки перечитываются свежими — исправление отметки меняет результат."""
    db, ports = _stand(rows=_rows_full_month("В"), marks=[])
    first = close_period(EMP, OCT, at(1, 0, month=11), ports)
    assert first.settle.cards[0].full_fact_minutes == 0
    db.marks = [IN(1, 8), OUT(1, 20)]                     # исправили данные после закрытия
    second = recalculate(EMP, OCT, at(5, 0, month=11), ports)
    assert second.settle.cards[0].full_fact_minutes == 720


def test_ex_53_control_view_closed_without_recalculation(monkeypatch):
    db, ports = _stand(rows=_rows_full_month("В"), marks=[])
    close_period(EMP, OCT, at(1, 0, month=11), ports)
    db.marks = [IN(1, 8), OUT(1, 20)]                     # правка данных не видна без пересчёта
    calls = _spy_settle(monkeypatch)
    view = view_period(EMP, OCT, at(4, 0, month=11), ports)
    assert calls["settle"] == 0
    assert view.settle.cards[0].full_fact_minutes == 0


# ── эффективный период и трудоустройство (R23/R27/R35, EX-55) ─────────────────

def _ex55_stand(employment, rows, marks=(), **kw):
    db = FakeDb(settings=_st())
    db.timesheet_rows = rows
    db.marks = list(marks)
    db.employment[EMP] = employment
    db.adjustments.append((EMP, max(dt.date(2026, 10, 1), employment.start), 0, "OPENING_SEED"))
    db.active = [EMP]
    return build_fakes(db)


def test_ex_55_effective_period_hiring_midmonth():
    rows = [day(10, "Я 12")] + _rows_full_month("В", first=11, last=31)
    db, ports = _ex55_stand(Employment(dt.date(2026, 10, 10), None), rows,
                            marks=[IN(10, 8), OUT(10, 20)])
    view = close_period(EMP, OCT, at(1, 0, month=11), ports)
    assert len(view.settle.cards) == 22
    assert view.settle.cards[0].day == dt.date(2026, 10, 10)
    assert view.settle.cards[0].work_minutes == 720
    assert view.settle.total_debt_minutes == 0


def test_ex_55_control_1_row_outside_employment():
    rows = [Day(dt.date(2026, 10, 5), "В", 0, EMP, "Смена 1"), day(10, "Я 12")] + \
        _rows_full_month("В", first=11, last=31)
    db, ports = _ex55_stand(Employment(dt.date(2026, 10, 10), None), rows)
    with pytest.raises(InvalidInputDataError) as exc:
        close_period(EMP, OCT, at(1, 0, month=11), ports)
    assert exc.value.code == "CHK-DAYS-IN-PERIOD"


def test_ex_55_control_2_incomplete_timesheet():
    rows = [day(10, "Я 12")] + _rows_full_month("В", first=16, last=31)   # 15.10 пропущен
    db, ports = _ex55_stand(Employment(dt.date(2026, 10, 10), None), rows)
    with pytest.raises(IncompleteTimesheetError):
        close_period(EMP, OCT, at(1, 0, month=11), ports)


def test_ex_55_control_3_dismissal_midmonth():
    rows = [day(10, "Я 12")] + _rows_full_month("В", first=11, last=20)
    db, ports = _ex55_stand(Employment(dt.date(2026, 10, 10), dt.date(2026, 10, 20)), rows)
    view = close_period(EMP, OCT, dt.datetime(2026, 10, 21, 0, 0, tzinfo=TZ).astimezone(dt.timezone.utc), ports)
    assert len(view.settle.cards) == 11


def test_ex_55_control_4_view_next_month_after_previous_closed():
    rows = [day(10, "Я 12")] + _rows_full_month("В", first=11, last=31) + _rows_full_month("В", month=11)
    db, ports = _ex55_stand(Employment(dt.date(2026, 10, 10), None), rows)
    with pytest.raises(PreviousPeriodNotClosedError):
        view_period(EMP, NOV, at(15, 12, month=11), ports)
    close_period(EMP, OCT, at(1, 0, month=11), ports)
    view = view_period(EMP, NOV, at(15, 12, month=11), ports)
    assert len(view.settle.cards) == 30


def test_period_outside_employment_rejected_before_other_checks(monkeypatch):
    """R35: отказ РАНЬШЕ RUL-VIEW-AFTER-PREVIOUS; домен не вызывается."""
    rows = _rows_full_month("В")
    db, ports = _ex55_stand(Employment(dt.date(2026, 8, 1), dt.date(2026, 9, 20)), rows)
    calls = _spy_settle(monkeypatch)
    with pytest.raises(PeriodOutsideEmploymentError):
        view_period(EMP, OCT, at(15, 12), ports)
    with pytest.raises(PeriodOutsideEmploymentError):
        close_period(EMP, OCT, at(1, 0, month=11), ports)
    with pytest.raises(PeriodOutsideEmploymentError):
        recalculate(EMP, OCT, at(1, 0, month=11), ports)
    assert calls["settle"] == 0


def test_timesheet_called_with_full_requested_period():
    """R27: TimesheetPort.days вызывается полным запрошенным периодом."""
    rows = [day(10, "Я 12")] + _rows_full_month("В", first=11, last=31)
    db, ports = _ex55_stand(Employment(dt.date(2026, 10, 10), None), rows)
    view_period(EMP, OCT, at(15, 12), ports)
    assert (EMP, OCT) in db.timesheet_calls


# ── выборка отметок (7.4, EX-38 контроль) ─────────────────────────────────────

def test_punch_selection_window_with_step_reserve():
    db, ports = _stand(rows=_rows_full_month("В"), marks=[])
    load_inputs(EMP, OCT, ports)
    between = [c for c in db.punch_calls if c[0] == "between"][0]
    st = _st()
    expected_from = dt.datetime(2026, 10, 1, 0, 0, tzinfo=TZ).astimezone(dt.timezone.utc) \
        - dt.timedelta(minutes=st.step_minutes)
    expected_to = dt.datetime(2026, 11, 1, 0, 0, tzinfo=TZ).astimezone(dt.timezone.utc) \
        + dt.timedelta(minutes=st.step_minutes)
    assert between[1] == expected_from
    assert between[2] == expected_to


def test_ex_38_control_mark_beyond_period_included_in_selection():
    """Контроль EX-38: уход 00:20 следующего дня попадает в выборку с запасом."""
    prd = Period(dt.date(2026, 10, 31), dt.date(2026, 10, 31))
    out_mark = OUT(1, 0, 20, month=11)
    prd = Period(dt.date(2026, 10, 31), dt.date(2026, 10, 31))
    db, ports = _stand(rows=[day(31, "В")], marks=[IN(31, 20), out_mark], seed_period=prd)
    inp = load_inputs(EMP, prd, ports)
    assert out_mark in inp.marks
    result = view_period(EMP, prd, at(1, 12, month=11), ports)
    assert dict(result.settle.mgmt_timesheet[dt.date(2026, 10, 31)]) == {"ДЯ": 120, "ДН": 120}


def test_mark_exactly_at_from_utc_in_selection_not_opening():
    """Граница [from, to): отметка ровно в from_utc — в выборке (v7/R7)."""
    prd = Period(dt.date(2026, 10, 2), dt.date(2026, 10, 3))
    from_utc = dt.datetime(2026, 10, 1, 23, 0, tzinfo=TZ).astimezone(dt.timezone.utc)
    mark = Mark(EMP, from_utc, "in")
    db, ports = _stand(rows=[day(2, "В"), day(3, "В")], marks=[mark, OUT(3, 23)])
    inp = load_inputs(EMP, prd, ports)
    assert mark in inp.marks
    assert inp.opening_mark is None


# ── previous_step из настроек предыдущего периода (7.4) ───────────────────────

def test_previous_step_from_previous_period_settings():
    db, ports = _stand(rows=_rows_full_month("В", month=9) + _rows_full_month("В"),
                       employment=Employment(dt.date(2020, 1, 1), None), seed=False)
    db.adjustments.append((EMP, SEP.start, 0, "OPENING_SEED"))
    db.settings_by_period[(SEP.start, SEP.end)] = dataclasses.replace(_st(), step_minutes=15)
    close_period(EMP, SEP, at(1, 0), ports)            # сентябрь с шагом 15
    db.adjustments.append((EMP, dt.date(2026, 10, 5), 45, "manual"))
    inp = load_inputs(EMP, OCT, ports)
    assert inp.previous_step == 15


# ── гранулярность периодов (R36) ──────────────────────────────────────────────

def test_month_and_half_month_periods():
    assert month_period(2026, 10) == Period(dt.date(2026, 10, 1), dt.date(2026, 10, 31))
    assert half_month_period(2026, 10, 1) == Period(dt.date(2026, 10, 1), dt.date(2026, 10, 15))
    assert half_month_period(2026, 10, 2) == Period(dt.date(2026, 10, 16), dt.date(2026, 10, 31))
    assert half_month_period(2026, 2, 2) == Period(dt.date(2026, 2, 16), dt.date(2026, 2, 28))


def test_period_chain_by_granularity():
    h1 = half_month_period(2026, 10, 1)
    h2 = half_month_period(2026, 10, 2)
    assert next_period(h1, GRANULARITY_HALF_MONTH) == h2
    assert next_period(h2, GRANULARITY_HALF_MONTH) == half_month_period(2026, 11, 1)
    assert previous_period(h1, GRANULARITY_HALF_MONTH) == half_month_period(2026, 9, 2)
    assert next_period(OCT, "month") == NOV
    assert previous_period(OCT, "month") == SEP
    assert period_containing(dt.date(2026, 10, 20), GRANULARITY_HALF_MONTH) == h2


def test_close_month_and_recalculate_month_wrappers():
    db, ports = _stand()
    view = close_month(EMP, 2026, 10, at(1, 0, month=11), ports)
    assert db.closings[(EMP, OCT.start)]["result"] == view.settle
    recalculated = recalculate_month(EMP, 2026, 10, at(2, 0, month=11), ports)
    assert recalculated.settle == view.settle


def test_is_first_period_by_employment():
    emp = Employment(dt.date(2026, 10, 10), None)
    assert is_first_period(OCT, emp, "month") is True
    assert is_first_period(NOV, emp, "month") is False


# ── посев OPENING_SEED (R37) ──────────────────────────────────────────────────

def test_seed_allowed_only_for_first_period():
    db, ports = _stand()                                 # октябрь — первый период
    bank_adjustment.validate_adjustment_entry(EMP, d(5), "OPENING_SEED", ports)
    with pytest.raises(SeedNotAllowedError):
        bank_adjustment.validate_adjustment_entry(EMP, dt.date(2026, 11, 5),
                                                  "OPENING_SEED", ports)


def test_adjustment_of_closed_period_rejected():
    db, ports = _stand()
    close_period(EMP, OCT, at(1, 0, month=11), ports)
    with pytest.raises(AdjustmentClosedPeriodError):
        bank_adjustment.validate_adjustment_entry(EMP, d(5), "manual", ports)


def test_opening_bank_set_flag_from_seed_presence():
    db, ports = _stand(seed=False)
    state = ports.store.period_state(EMP, OCT)
    assert state.opening_bank_set is False
    db.adjustments.append((EMP, d(5), 0, "OPENING_SEED"))
    assert ports.store.period_state(EMP, OCT).opening_bank_set is True


# ── доска (R38, 16.2) ─────────────────────────────────────────────────────────

def test_board_population_only_active_employees():
    db, ports = _stand(marks=[IN(15, 8)])
    db.marks.append(Mark("e9", at(15, 7), "in"))          # уволенный с незакрытой сессией
    db.active = [EMP]                                     # e9 не трудоустроен сегодня
    db.shifts = [Shift(EMP, at(15, 8), at(15, 20)), Shift("e9", at(15, 8), at(15, 20))]
    board = presence_board(at(15, 12), ports)
    assert board.at_work_now == 1
    assert [c.employee_id for c in board.open_session_cards] == [EMP]
    assert board.expected_now == 1


def test_board_query_budget_max_five():
    db, ports = _stand(marks=[IN(15, 8)])
    db.queries.clear()
    presence_board(at(15, 12), ports)
    assert len(db.queries) <= 5, db.queries


def test_board_uses_only_batch_methods_and_no_heavy_pipeline(monkeypatch):
    """16.1 п.2/п.4: доска не вызывает settle()/evaluate_flags() и строится только
    батч-методами портов (без цикла «по сотруднику → запрос»)."""
    db, ports = _stand(marks=[IN(15, 8)])
    calls = _spy_settle(monkeypatch)
    db.queries.clear()
    presence_board(at(15, 12), ports)
    assert calls["settle"] == 0
    forbidden = {"timesheet.days", "punch.marks_between", "punch.last_mark_before",
                 "punch.first_mark_after", "shift.shifts", "absence.absences",
                 "bank.opening", "bank.adjustments", "store.period_state",
                 "carry_over.load_deferred", "employment.employment"}
    assert not (set(db.queries) & forbidden), db.queries


# ── карточка УТ: два плана (R39) ──────────────────────────────────────────────

def test_day_views_carry_informational_timesheet_plan():
    from app.engine.domain.settings.types import Window
    st = dataclasses.replace(_st(), windows={**dict(_st().windows), "Я 10,75": Window(480, 1200)})
    db = FakeDb(settings=st)
    db.timesheet_rows = [Day(d(1), "Я", 645, EMP, "Смена 1"), Day(d(2), "В", 0, EMP, "Смена 1")]
    db.employment[EMP] = Employment(dt.date(2020, 1, 1), None)
    db.adjustments.append((EMP, d(1), 0, "OPENING_SEED"))
    db.active = [EMP]
    _, ports = build_fakes(db)
    view = view_period(EMP, Period(d(1), d(2)), at(3, 0), ports)
    views = day_views(view)
    assert views[0].card.plan_minutes == 720               # расчётный план = окно (R34)
    assert views[0].timesheet_plan_minutes == 645            # информационный план строки (R39)
    assert views[1].timesheet_plan_minutes == 0


# ── история сессий (16.4) ─────────────────────────────────────────────────────

def test_view_sessions_basic_and_range_flags():
    marks = [Mark(EMP, at(1, 20), "in"),                     # открыта до диапазона
             Mark(EMP, at(2, 8), "out"),
             Mark(EMP, at(3, 9), "in"),
             Mark(EMP, at(3, 18), "out"),
             Mark(EMP, at(5, 9), "in")]                      # после диапазона — не показывается
    db, ports = _stand(rows=_rows_full_month("В", first=1, last=6), marks=marks)
    sessions = view_sessions.view_sessions(EMP, at(2, 0), at(5, 0), ports)
    assert len(sessions) == 2
    assert sessions[0].started_before_range is True
    assert sessions[0].session.start == at(1, 20)
    assert sessions[0].session.end == at(2, 8)
    assert sessions[1].session.start == at(3, 9)
    assert sessions[1].session.end == at(3, 18)
    assert sessions[1].started_before_range is False


def test_view_sessions_closed_after_range():
    marks = [IN(2, 9), Mark(EMP, at(6, 8), "out")]           # уход за правой границей
    db, ports = _stand(rows=_rows_full_month("В", first=1, last=7), marks=marks)
    sessions = view_sessions.view_sessions(EMP, at(2, 0), at(5, 0), ports)
    assert len(sessions) == 1
    assert sessions[0].session.end == at(6, 8)
    assert sessions[0].closed_after_range is True


def test_view_sessions_truly_open():
    db, ports = _stand(rows=_rows_full_month("В"), marks=[IN(2, 9)])
    sessions = view_sessions.view_sessions(EMP, at(1, 0), at(5, 0), ports)
    assert len(sessions) == 1
    assert sessions[0].session.end is None
    assert sessions[0].closed_after_range is False


def test_view_sessions_closing_in_ignored():
    marks = [IN(2, 9), Mark(EMP, at(6, 8), "in")]            # closing = «пришёл» — игнорируется
    db, ports = _stand(rows=_rows_full_month("В", first=1, last=7), marks=marks)
    sessions = view_sessions.view_sessions(EMP, at(2, 0), at(5, 0), ports)
    assert sessions[-1].session.end is None


def test_view_sessions_invalid_sequence_raises():
    marks = [IN(2, 9), IN(3, 9), OUT(3, 18)]
    db, ports = _stand(rows=_rows_full_month("В", first=1, last=5), marks=marks)
    with pytest.raises(InvalidInputDataError) as exc:
        view_sessions.view_sessions(EMP, at(2, 0), at(4, 0), ports)
    assert exc.value.code == "CHK-PUNCH-SEQUENCE"


# ── График (16.3) ─────────────────────────────────────────────────────────────

def test_schedule_generation_from_timesheet_windows():
    db, ports = _stand(rows=[day(1, "Я 12"), day(2, "В")])
    outcome = schedule_view.rebuild_generated_schedule(EMP, Period(d(1), d(2)), ports)
    assert outcome.generated == 1
    entries = db.generated[(EMP, d(1), d(2))]
    assert entries[0].source == "generated"
    assert entries[0].shift.start_utc == dt.datetime(2026, 10, 1, 8, 0,
                                                     tzinfo=TZ).astimezone(dt.timezone.utc)


def test_schedule_manual_day_requires_accepts_ut_anchor():
    db, ports = _stand(rows=[day(1, "Я 12"), day(2, "ДО")])
    night = Shift(EMP, at(1, 20), at(2, 8))
    schedule_view.save_schedule_day(EMP, d(1), [night], ports)          # якорь 01.10 — редактируем
    assert db.manual_shifts[(EMP, d(1))] == [night]
    with pytest.raises(ScheduleDayNotEditableError):
        schedule_view.save_schedule_day(EMP, d(2), [night], ports)      # якорь 02.10 «ДО» — нет


def test_schedule_rebuild_drops_manual_on_non_editable_code():
    db, ports = _stand(rows=[day(1, "Я 12")])
    schedule_view.save_schedule_day(EMP, d(1), [Shift(EMP, at(1, 9), at(1, 18))], ports)
    db.timesheet_rows = [day(1, "ДО")]                                   # код стал нередактируемым
    outcome = schedule_view.rebuild_generated_schedule(EMP, Period(d(1), d(1)), ports)
    assert outcome.manual_dropped == (d(1),)
    assert outcome.generated == 0


def test_schedule_logical_cut_via_absence():
    db, ports = _stand(rows=[day(1, "Я 12")])
    absence_id = schedule_view.save_absence(EMP, d(1), "12:00", "15:00", False, ports)
    assert db.absences_store[0][1] == EMP
    schedule_view.drop_absence(absence_id, ports)
    assert db.absences_store == []


# ── Табель (16.5) ─────────────────────────────────────────────────────────────

def test_timesheet_edit_validation_uses_domain_checks():
    db, ports = _stand(rows=_rows_full_month("В"))
    with pytest.raises(UnknownDayCodeError):
        timesheet_edit.save_timesheet_day(EMP, d(1), "ХХ", None, ports)
    with pytest.raises(InvalidInputDataError) as exc:
        timesheet_edit.save_timesheet_day(EMP, d(1), "Я", None, ports)
    assert exc.value.code == "CHK-PLAN-CONSISTENT"
    with pytest.raises(InvalidInputDataError) as exc:
        timesheet_edit.save_timesheet_day(EMP, d(1), "В", 480, ports)
    assert exc.value.code == "CHK-PLAN-CONSISTENT"
    with pytest.raises(InvalidInputDataError) as exc:
        timesheet_edit.save_timesheet_day(EMP, d(1), "Я", 500, ports)
    assert exc.value.code == "CHK-PLAN-FORMAT"
    with pytest.raises(UnknownTimesheetValueError):
        timesheet_edit.save_timesheet_day(EMP, d(1), "Я", 780, ports)     # «Я 13» без окна


def test_timesheet_edit_open_period_and_regeneration():
    db, ports = _stand(rows=_rows_full_month("В"))
    outcome = timesheet_edit.save_timesheet_day(EMP, d(1), "Я", 720, ports)
    assert outcome.needs_recalculate is False
    assert db.saved_days[-1] == (EMP, d(1), "Я", 720)
    # перегенерация дня D и соседей (смена через полночь даёт отрезки двум дням, 16.3/16.5)
    assert (EMP, d(1) - dt.timedelta(days=1), d(1) + dt.timedelta(days=1)) in db.generated


def test_timesheet_edit_last_closed_warns_recalculate():
    db, ports = _stand(rows=_rows_full_month("В"))
    close_period(EMP, OCT, at(1, 0, month=11), ports)
    outcome = timesheet_edit.save_timesheet_day(EMP, d(1), "Я", 720, ports)
    assert outcome.needs_recalculate is True


def test_timesheet_edit_locked_for_earlier_closed_periods():
    db, ports = _stand(rows=_rows_full_month("В") + _rows_full_month("В", month=11))
    close_period(EMP, OCT, at(1, 0, month=11), ports)
    close_period(EMP, NOV, at(1, 0, month=12), ports)
    with pytest.raises(TimesheetLockedError):
        timesheet_edit.save_timesheet_day(EMP, d(1), "Я", 720, ports)
