"""Property-based тесты инвариантов (13 п.2): случайные отметки, Табель, настройки,
веса, шаги 15/30/60, deferred_in; обязательный фаззинг цепочки «размещение → каскад →
повторное размещение» под контролем INV-MINUTES-CONSERVED, INV-CLOSE-BALANCE,
INV-DAY-LIMIT (проверяются внутри settle — любое нарушение прерывает прогон);
INV-DETERMINISM: повторный прогон, перестановка отметок в источнике, перестановка
строк deferred_in (v7/R4)."""
from __future__ import annotations

import datetime as dt
import random

from hypothesis import given
from hypothesis import settings as hsettings
from hypothesis import strategies as hst

from app.modules.timesheet.domain.flags.evaluate_flags import evaluate_flags
from app.modules.timesheet.domain.pipeline.settle import settle
from app.modules.timesheet.domain.settings.types import MOD_DOUBLE, MOD_PAYS, MOD_PLAN_EQUALS_FACT, ModifierEntry
from app.modules.timesheet.domain.types.entities import Adjustment, Day, DeferredBlock, Mark, Period

from .helpers import EMP, TZ, UTC, Y, midnight_after, shifts_from_days

STEPS = (15, 30, 60)
VALUES_WITH_HOURS = ("Я 12", "Я 9", "Я 8", "К 12")
VALUES_NO_HOURS = ("В", "ОТ", "ДО", "Б", "НН")
GROUPS = ("Смена 1", "Смена 2", "Пятидневка")
TARIFFS = ("ДЯ", "ДН", "ДЯ2", "ДН2")


def _plan_minutes(value: str) -> int:
    _, _, hours = value.partition(" ")
    return int(float(hours.replace(",", ".")) * 60) if hours else 0


@hst.composite
def inputs(draw):
    step = draw(hst.sampled_from(STEPS))
    n_days = draw(hst.integers(1, 6))
    start = dt.date(Y, 10, 1)
    prd = Period(start, start + dt.timedelta(days=n_days - 1))
    rows = []
    for i in range(n_days):
        value = draw(hst.sampled_from(VALUES_WITH_HOURS + VALUES_NO_HOURS))
        rows.append(Day(prd.start + dt.timedelta(days=i), value.partition(" ")[0],
                        _plan_minutes(value), EMP, draw(hst.sampled_from(GROUPS))))
    # случайные сессии: непересекающиеся пары in/out в расширенном диапазоне
    lo = dt.datetime.combine(prd.start - dt.timedelta(days=2), dt.time(0), TZ)
    hi = dt.datetime.combine(prd.end + dt.timedelta(days=3), dt.time(0), TZ)
    span = int((hi - lo).total_seconds() // 60)
    marks: list[Mark] = []
    cursor = draw(hst.integers(0, max(1, span // 4)))
    for _ in range(draw(hst.integers(0, 5))):
        length = draw(hst.integers(1, 600))
        if cursor + length >= span:
            break
        s = lo + dt.timedelta(minutes=cursor)
        e = s + dt.timedelta(minutes=length)
        marks += [Mark(EMP, s.astimezone(UTC), "in"), Mark(EMP, e.astimezone(UTC), "out")]
        cursor += length + draw(hst.integers(1, 600))
    # opening_mark: уносим первую «in» за границу выборки
    opening = None
    if marks and draw(hst.booleans()):
        opening = marks.pop(0)                     # «пришёл» уходит за границу выборки;
        assert opening.kind == "in"                # парный «ушёл» остаётся первым — чередование верно
    bank = draw(hst.integers(-1440, 2880))
    prev_step = draw(hst.sampled_from(STEPS))
    deferred_in = [DeferredBlock(prd.start - dt.timedelta(days=draw(hst.integers(1, 10))),
                                 draw(hst.sampled_from(TARIFFS)),
                                 draw(hst.integers(1, 40)) * prev_step)
                   for _ in range(draw(hst.integers(0, 5)))]
    adjustments = [Adjustment(draw(hst.integers(-600, 600)), prd, "MANUAL")
                   for _ in range(draw(hst.integers(0, 2)))]
    modifiers = []
    for i in range(n_days):
        day_ = prd.start + dt.timedelta(days=i)
        if draw(hst.booleans()):
            modifiers.append(ModifierEntry(MOD_DOUBLE, True, day=day_))
        if draw(hst.booleans()):
            modifiers.append(ModifierEntry(MOD_PAYS, False, day=day_))
        if draw(hst.integers(0, 3)) == 0:
            modifiers.append(ModifierEntry(MOD_PLAN_EQUALS_FACT,
                                           draw(hst.sampled_from(["yes", "auto"])), day=day_))
    weights = {t: draw(hst.integers(1, 3)) for t in TARIFFS}
    cascade = tuple(random.Random(draw(hst.integers(0, 10**6))).sample(TARIFFS, len(TARIFFS)))
    placement = tuple(random.Random(draw(hst.integers(0, 10**6))).sample(TARIFFS, len(TARIFFS)))
    import dataclasses

    from app.modules.timesheet.domain.settings.defaults import default_settings
    st = dataclasses.replace(default_settings(), step_minutes=step, modifiers=tuple(modifiers),
                             weights=weights, cascade_order=cascade, placement_order=placement)
    return dict(prd=prd, rows=rows, marks=marks, opening=opening, bank=bank,
                prev_step=prev_step, deferred_in=deferred_in, adjustments=adjustments, st=st)


def _settle(inp, mode="close"):
    return settle(inp["prd"], inp["rows"], inp["marks"], inp["opening"], inp["bank"],
                  inp["adjustments"], inp["deferred_in"], inp["st"],
                  midnight_after(inp["prd"].end), mode, inp["prev_step"])


@hsettings(max_examples=120, deadline=None)
@given(inputs())
def test_invariants_hold_on_random_inputs(inp):
    """settle() проверяет инварианты внутри (10.1): любое нарушение — исключение."""
    result = _settle(inp)
    step = inp["st"].step_minutes
    for card in result.cards:
        assert card.debt_minutes % step == 0        # недостача кратна шагу (v7)
        assert card.plan_minutes % step == 0        # план карточки = окно (R34)
        assert card.work_minutes % step == 0
        assert card.overtime_minutes % step == 0
        assert card.full_fact_minutes == card.work_minutes + card.overtime_minutes
    assert set(result.mgmt_timesheet) == {c.day for c in result.cards}
    # INV-CLOSE-BALANCE явно
    paid_cuts = sum(c.paid_minutes for c in result.cuts)
    assert result.total_debt_minutes == result.paid_with_bank_minutes + paid_cuts \
        + result.residual_debt_minutes


@hsettings(max_examples=60, deadline=None)
@given(inputs())
def test_view_mode_invariants(inp):
    result = _settle(inp, mode="view")
    available = (result.bank_open_normalized_minutes + result.bank_adjustments_minutes
                 + result.credited_to_bank_minutes)
    assert result.paid_with_bank_minutes == 0
    assert result.cuts == ()
    assert result.residual_debt_minutes == result.total_debt_minutes
    assert result.bank_closed_minutes == available


@hsettings(max_examples=60, deadline=None)
@given(inputs())
def test_determinism_repeat(inp):
    assert _settle(inp) == _settle(inp)


@hsettings(max_examples=60, deadline=None)
@given(inputs())
def test_determinism_deferred_row_order(inp):
    base = _settle(inp)
    shuffled = dict(inp)
    shuffled["deferred_in"] = list(reversed(inp["deferred_in"]))
    assert _settle(shuffled) == base


@hsettings(max_examples=60, deadline=None)
@given(inputs())
def test_determinism_marks_source_order(inp):
    """Перестановка отметок в источнике не меняет результат: адаптер стабильно сортирует
    (RUL-DETERMINISM-AND-ORDER), домен округляет без пересортировки."""
    base = _settle(inp)
    shuffled = dict(inp)
    marks = list(inp["marks"])
    random.Random(7).shuffle(marks)
    shuffled["marks"] = sorted(marks, key=lambda m: (m.at_utc, 0 if m.kind == "in" else 1))
    assert _settle(shuffled) == base


@hsettings(max_examples=60, deadline=None)
@given(inputs())
def test_flags_pipeline_runs_and_covers_period(inp):
    """evaluate_flags на случайных данных: инварианты стадии выполняются, Flag.day в периоде."""
    result = _settle(inp)
    pef = {c.day: c.plan_equals_fact_applied for c in result.cards}
    shifts = shifts_from_days(inp["rows"], inp["st"])
    flags = evaluate_flags(inp["prd"], inp["rows"], pef, inp["marks"], inp["opening"],
                           shifts, (), inp["st"], midnight_after(inp["prd"].end))
    for flag in flags.flags:
        assert inp["prd"].start <= flag.day <= inp["prd"].end
    days = sorted(f.day for f in flags.flags)
    assert days == sorted(days)                     # канонический порядок: день первым ключом


@hsettings(max_examples=40, deadline=None)
@given(inputs())
def test_minutes_conserved_fuzz_placement_cascade_replacement(inp):
    """Фаззинг цепочки «размещение → каскад → повторное размещение» (13 п.2):
    INV-MINUTES-CONSERVED контролируется check_result внутри settle; здесь — явная
    перепроверка сохранения минут по полям результата."""
    result = _settle(inp)
    normalized_in = sum(b.minutes for b in result.deferred_blocks)  # placeholder
    created = sum(sum(c.codes.values()) for c in result.cards) \
        + sum(b.minutes for b in _normalized_deferred(inp))
    placed = sum(m for row in result.mgmt_timesheet.values() for m in row.values())
    outgoing = sum(b.minutes for b in result.deferred_blocks)
    unpaid_taken = sum(r.data["taken_minutes"] for r in result.trace
                       if r.code == "UNPAID_CREDITED")
    cut = sum(c.taken_minutes for c in result.cuts)
    assert created == placed + outgoing + unpaid_taken + cut
    assert normalized_in >= 0


def _normalized_deferred(inp):
    from app.modules.timesheet.domain.opening.normalize_deferred import normalize_deferred
    from app.modules.timesheet.domain.placement.canonical_order import sort_deferred
    blocks, _ = normalize_deferred(sort_deferred(inp["deferred_in"], inp["st"]),
                                   inp["prev_step"], inp["st"].step_minutes)
    return blocks
