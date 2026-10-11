"""Валидация трёх уровней (5.3): конфигурация (уровень 1), входные данные
(уровень 2, стадия 1), данные Графика (уровень 3 — в test_adapters.py).
По тесту на каждое правило + положительные кейсы."""
from __future__ import annotations

import datetime as dt

import pytest

from app.engine.domain.settings.types import (
    MOD_PAYS,
    MOD_PLAN_EQUALS_FACT,
    Category,
    GlobalDefaults,
    ModifierEntry,
    Window,
)
from app.engine.domain.settings.validate import validate_settings
from app.engine.domain.types.entities import Adjustment, Day, DeferredBlock, Period
from app.engine.domain.types.errors import (
    ConfigError,
    IncompletePeriodError,
    IncompleteTimesheetError,
    InvalidInputDataError,
    UnknownDayCodeError,
    UnknownTimesheetValueError,
)

from .helpers import (
    EMP,
    IN,
    OUT,
    at,
    d,
    day,
    period,
    run_settle,
    settings,
)

OCT = period(d(1), d(31))


def _codes_of(st):
    return [code for code, _ in st.violations]


# ── уровень 1: положительный кейс и каждое правило ────────────────────────────

def test_default_settings_valid():
    validate_settings(settings())


def test_chk_window_plan_violation():
    st = settings(windows={"Я 12": Window(8 * 60, 14 * 60)})
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    assert "CHK-WINDOW-PLAN" in _codes_of(exc.value)


def test_chk_window_bounds_violation():
    st = settings(windows={"Я 12": Window(20 * 60, 8 * 60)})
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    assert "CHK-WINDOW-BOUNDS" in _codes_of(exc.value)


def test_chk_window_key_violations():
    for bad_key in ("Я 10.75", "Я12", "В", "Я 10,750", "Я 12,0", "Х 12"):
        st = settings(windows={**dict(settings().windows), bad_key: Window(480, 1200)})
        with pytest.raises(ConfigError) as exc:
            validate_settings(st)
        assert "CHK-WINDOW-KEY" in _codes_of(exc.value), bad_key


def test_chk_categories_cover_hole():
    st = settings(categories=(Category("ДЯ", 360, 1200),))
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    assert "CHK-CATEGORIES-COVER" in _codes_of(exc.value)


def test_chk_categories_cover_overlap():
    st = settings(categories=(Category("ДЯ", 360, 1320), Category("ДН", 1200, 360)))
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    assert "CHK-CATEGORIES-COVER" in _codes_of(exc.value)


def test_chk_codes_exist_violation():
    weights = dict(settings().weights)
    del weights["ДН2"]
    with pytest.raises(ConfigError) as exc:
        validate_settings(settings(weights=weights))
    assert "CHK-CODES-EXIST" in _codes_of(exc.value)


def test_chk_cascade_full_violation():
    with pytest.raises(ConfigError) as exc:
        validate_settings(settings(cascade_order=("ДЯ", "ДН", "ДЯ2")))
    assert "CHK-CASCADE-FULL" in _codes_of(exc.value)


def test_chk_cascade_full_duplicate():
    with pytest.raises(ConfigError) as exc:
        validate_settings(settings(cascade_order=("ДЯ", "ДЯ", "ДН", "ДЯ2", "ДН2")))
    assert "CHK-CASCADE-FULL" in _codes_of(exc.value)


def test_chk_weights_positive_violation():
    weights = dict(settings().weights)
    weights["ДН"] = 0
    with pytest.raises(ConfigError) as exc:
        validate_settings(settings(weights=weights))
    assert "CHK-WEIGHTS-POSITIVE" in _codes_of(exc.value)


def test_chk_step_divides_60_violation():
    with pytest.raises(ConfigError) as exc:
        validate_settings(settings(step_minutes=45))
    assert "CHK-STEP-DIVIDES-60" in _codes_of(exc.value)


def test_chk_grid_violation():
    st = settings(windows={**dict(settings().windows), "Я 9": Window(9 * 60 + 30, 18 * 60)})
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    assert "CHK-GRID" in _codes_of(exc.value)


def test_chk_placement_full_violation():
    with pytest.raises(ConfigError) as exc:
        validate_settings(settings(placement_order=("ДЯ", "ДН")))
    assert "CHK-PLACEMENT-FULL" in _codes_of(exc.value)


def test_chk_defaults_violation():
    st = settings(global_defaults=GlobalDefaults(double_overtime=None, pays_overtime=True,
                                                 plan_equals_fact="no"))
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    assert "CHK-DEFAULTS" in _codes_of(exc.value)


def test_chk_modifier_scope_violation_no_scope():
    st = settings([ModifierEntry(MOD_PAYS, True)])
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    assert "CHK-MODIFIER-SCOPE" in _codes_of(exc.value)


def test_chk_modifier_scope_unknown_group():
    st = settings([ModifierEntry(MOD_PAYS, True, group="Нет такой", day=d(1))])
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    assert "CHK-MODIFIER-SCOPE" in _codes_of(exc.value)


def test_chk_modifier_type_violation():
    st = settings([ModifierEntry(MOD_PLAN_EQUALS_FACT, True, day=d(1))])
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    assert "CHK-MODIFIER-TYPE" in _codes_of(exc.value)


def test_chk_modifier_conflict_group_period_overlap():
    prd = Period(d(1), d(20))
    st = settings([ModifierEntry(MOD_PAYS, True, group="Смена 1", period=prd),
                   ModifierEntry(MOD_PAYS, False, group="Смена 1", period=Period(d(15), d(31)))])
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    assert "CHK-MODIFIER-CONFLICT" in _codes_of(exc.value)


def test_all_violations_reported_at_once():
    st = settings(step_minutes=45, cascade_order=("ДЯ",))
    with pytest.raises(ConfigError) as exc:
        validate_settings(st)
    codes = _codes_of(exc.value)
    assert "CHK-STEP-DIVIDES-60" in codes
    assert "CHK-CASCADE-FULL" in codes


# ── уровень 2: стадия 1 settle() ──────────────────────────────────────────────

def _run(rows, prd=None, **kw):
    return run_settle(prd or Period(d(1), d(2)), rows, kw.pop("marks", []), **kw)


def test_chk_period_bounds():
    with pytest.raises(InvalidInputDataError) as exc:
        _run([day(1, "В")], prd=Period(d(2), d(1)))
    assert exc.value.code == "CHK-PERIOD-BOUNDS"


def test_chk_day_code_known():
    with pytest.raises(UnknownDayCodeError):
        _run([day(1, "ХХ"), day(2, "В")])


def test_chk_timesheet_covers_missing_day():
    with pytest.raises(IncompleteTimesheetError):
        _run([day(1, "В")])


def test_chk_timesheet_covers_duplicate_day():
    with pytest.raises(IncompleteTimesheetError):
        _run([day(1, "В"), day(1, "В"), day(2, "В")])


def test_chk_days_in_period():
    with pytest.raises(InvalidInputDataError) as exc:
        _run([day(1, "В"), day(2, "В"), Day(dt.date(2026, 10, 5), "В", 0, EMP, "Смена 1")],
             prd=Period(d(1), d(2)))
    assert exc.value.code == "CHK-DAYS-IN-PERIOD"


def test_chk_window_exists():
    with pytest.raises(UnknownTimesheetValueError) as exc:
        _run([day(1, "Я 13"), day(2, "В")])
    assert exc.value.value == "Я 13"


def test_chk_plan_consistent_zero_hours_for_carries_code():
    with pytest.raises(InvalidInputDataError) as exc:
        _run([Day(d(1), "Я", 0, EMP, "Смена 1"), day(2, "В")])
    assert exc.value.code == "CHK-PLAN-CONSISTENT"


def test_chk_plan_consistent_hours_for_non_carries_code():
    with pytest.raises(InvalidInputDataError) as exc:
        _run([Day(d(1), "В", 480, EMP, "Смена 1"), day(2, "В")])
    assert exc.value.code == "CHK-PLAN-CONSISTENT"


def test_chk_plan_format_500_not_multiple_of_15():
    with pytest.raises(InvalidInputDataError) as exc:
        _run([Day(d(1), "Я", 500, EMP, "Смена 1"), day(2, "В")])
    assert exc.value.code == "CHK-PLAN-FORMAT"


def test_plan_495_is_norm():
    rows = [Day(d(1), "Я", 495, EMP, "Смена 1"), day(2, "В")]
    st = settings(windows={**dict(settings().windows), "Я 8,25": Window(480, 1200)})
    _run(rows, st=st)                              # 495 кратно 15 — значение «Я 8,25»


def test_chk_single_employee():
    rows = [day(1, "В"), Day(d(2), "В", 0, "e2", "Смена 1")]
    with pytest.raises(InvalidInputDataError) as exc:
        _run(rows)
    assert exc.value.code == "CHK-SINGLE-EMPLOYEE"


def test_chk_group_exists():
    rows = [day(1, "В", group="Несуществующая"), day(2, "В")]
    with pytest.raises(InvalidInputDataError) as exc:
        _run(rows)
    assert exc.value.code == "CHK-GROUP-EXISTS"


def test_two_groups_in_period_is_norm():
    rows = [day(1, "В", group="Смена 1"), day(2, "В", group="Пятидневка")]
    _run(rows)                                     # RUL-GROUP-PER-DAY — не ошибка


def test_chk_deferred_in_violations():
    for block in (DeferredBlock(d(1), "ДЯ", 0), DeferredBlock(d(1), "ДЯ", -60),
                  DeferredBlock(d(1), "ДЯ", 90), DeferredBlock(d(2), "ДЯ", 60)):
        with pytest.raises(InvalidInputDataError) as exc:
            _run([day(1, "В"), day(2, "В")], deferred=[block])
        assert exc.value.code == "CHK-DEFERRED-IN"


def test_chk_opening_bad_previous_step():
    with pytest.raises(InvalidInputDataError) as exc:
        _run([day(1, "В"), day(2, "В")], prev_step=0)
    assert exc.value.code == "CHK-OPENING"
    with pytest.raises(InvalidInputDataError) as exc:
        _run([day(1, "В"), day(2, "В")], prev_step=45)
    assert exc.value.code == "CHK-OPENING"


def test_chk_opening_adjustment_of_other_period_is_error_not_filter():
    foreign = Adjustment(-60, Period(dt.date(2026, 9, 1), dt.date(2026, 9, 30)), "MANUAL")
    with pytest.raises(InvalidInputDataError) as exc:
        _run([day(1, "В"), day(2, "В")], adjustments=[foreign])
    assert exc.value.code == "CHK-OPENING"


def test_chk_now_in_period():
    with pytest.raises(InvalidInputDataError) as exc:
        _run([day(1, "В"), day(2, "В")], now=at(1, 0) - dt.timedelta(minutes=1),
             mode="view")
    assert exc.value.code == "CHK-NOW-IN-PERIOD"


def test_chk_close_allowed():
    with pytest.raises(IncompletePeriodError):
        _run([day(1, "В"), day(2, "В")], now=at(2, 23, 40), mode="close")


def test_close_exactly_at_midnight_after_end_allowed():
    _run([day(1, "В"), day(2, "В")], now=at(3, 0), mode="close")


def test_chk_punch_sequence_inside_settle_stage4():
    marks = [IN(1, 8), IN(1, 12), OUT(1, 20)]
    with pytest.raises(InvalidInputDataError) as exc:
        _run([day(1, "В"), day(2, "В")], marks=marks)
    assert exc.value.code == "CHK-PUNCH-SEQUENCE"


def test_mark_exactly_at_from_utc_is_in_selection_not_opening():
    """Граница выборки полуоткрытая [from, to) (2.6, v7/R7) — доменная часть:
    отметка ровно в полночь начала периода входит в выборку как обычная."""
    prd = Period(d(1), d(1))
    result = run_settle(prd, [day(1, "Я 12")], [IN(1, 0), OUT(1, 8)], now=at(2, 0))
    assert result.cards[0].full_fact_minutes == 480


def test_explicit_yes_on_code_without_hours_ignored():
    """Явное «План=Факт = Да» у кода без часов игнорируется (v7): предикат ложен,
    записи в трассе нет (карточка и так нулевая)."""
    from .helpers import PEF_YES_, pef
    st = settings([pef(PEF_YES_, 1)])
    result = run_settle(Period(d(1), d(1)), [day(1, "В")], [], st=st)
    assert result.cards[0].plan_equals_fact_applied is False
    assert not [r for r in result.trace if r.code == "PLAN_EQUALS_FACT"]
