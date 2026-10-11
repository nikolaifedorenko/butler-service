"""Инварианты карточек (10.1: после стадии 5) и покрытие plan_equals_fact
(в evaluate_flags на входе)."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from ..codes_registry.invariant_codes import (
    INV_CARDS_COVER_PERIOD,
    INV_CODES_EQ_OVERTIME,
    INV_DEBT_NON_NEGATIVE,
    INV_FACT_SPLIT,
    INV_GRID,
    INV_PLAN_EQUALS_FACT_ZERO,
    INV_WORK_LE_FACT,
    INV_WORK_LE_WINDOW,
)
from ..day_card.window_of_day import window_of_day
from ..settings.types import Settings
from ..types.entities import Day, Period
from ..types.results import DayCard
from ._fail import fail


def _check_grid(card: DayCard, step: int) -> None:
    values = (card.full_fact_minutes, card.work_minutes, card.overtime_minutes,
              card.debt_minutes, card.plan_minutes, *card.codes.values())
    if any(v % step for v in values):
        fail(INV_GRID, {"day": card.day, "card": {k: v for k, v in
             (("fact", card.full_fact_minutes), ("work", card.work_minutes),
              ("plan", card.plan_minutes), ("debt", card.debt_minutes)) if v % step}})


def _check_one(card: DayCard, day: Day, st: Settings) -> None:
    window = window_of_day(day, st)
    limit = window.length if window is not None else 0
    if card.debt_minutes < 0:
        fail(INV_DEBT_NON_NEGATIVE, {"day": card.day, "debt": card.debt_minutes})
    if card.work_minutes > card.full_fact_minutes:
        fail(INV_WORK_LE_FACT, {"day": card.day})
    if card.work_minutes > limit:
        fail(INV_WORK_LE_WINDOW, {"day": card.day, "work": card.work_minutes, "window": limit})
    if sum(card.codes.values()) != card.overtime_minutes:
        fail(INV_CODES_EQ_OVERTIME, {"day": card.day})
    if card.work_minutes + card.overtime_minutes != card.full_fact_minutes:
        fail(INV_FACT_SPLIT, {"day": card.day})
    _check_grid(card, st.step_minutes)
    if card.plan_equals_fact_applied and (card.plan_minutes or card.full_fact_minutes
                                          or card.work_minutes or card.overtime_minutes
                                          or card.debt_minutes or card.codes):
        fail(INV_PLAN_EQUALS_FACT_ZERO, {"day": card.day})


def check_cards(cards: Sequence[DayCard], days: Mapping[dt.date, Day], st: Settings) -> None:
    for card in cards:
        _check_one(card, days[card.day], st)


def check_pef_coverage(period: Period, days: Sequence[Day],
                       plan_equals_fact: Mapping[dt.date, bool]) -> None:
    """INV-CARDS-COVER-PERIOD: ключ plan_equals_fact обязан быть на каждый день периода
    и быть согласованным с days (6.6); отсутствие ключа — ошибка реализации."""
    expected = {period.start + dt.timedelta(days=i)
                for i in range((period.end - period.start).days + 1)}
    missing = expected - set(plan_equals_fact)
    if missing or {d.day for d in days} != expected:
        fail(INV_CARDS_COVER_PERIOD, {"missing_pef_days": tuple(sorted(missing))[:8],
                                      "days_rows": len(days), "period_days": len(expected)})
