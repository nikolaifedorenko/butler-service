"""build_trace(stage_records, cards, days, st) — трассировка по стадиям (3.4; сигнатура
зафиксирована в v7.1). Записи стадии 5 PLAN_EQUALS_FACT не возвращаются функцией стадии —
восстанавливаются здесь из полей карточек и resolve_plan_equals_fact (6.2, v7/R8)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ..codes_registry.reason_codes import PLAN_EQUALS_FACT, STEP_CARDS
from ..day_card.plan_of_day import plan_of_day
from ..day_card.resolve_plan_equals_fact import resolve_plan_equals_fact
from ..settings.types import Settings
from ..types.entities import Day
from ..types.results import DayCard, Reason


@dataclass(frozen=True)
class StageRecords:
    """Записи стадий, возвращаемые явно (6.2): стадия 2 — opening, 7 — credit_unpaid,
    8 — placement, 10 — bank, 11 — cascade, 12 — replacement, 13 — closing."""

    opening: tuple[Reason, ...] = field(default=())
    credit_unpaid: tuple[Reason, ...] = field(default=())
    placement: tuple[Reason, ...] = field(default=())
    bank: tuple[Reason, ...] = field(default=())
    cascade: tuple[Reason, ...] = field(default=())
    replacement: tuple[Reason, ...] = field(default=())
    closing: tuple[Reason, ...] = field(default=())


def pef_reasons(cards: Sequence[DayCard], days: Mapping[dt.date, Day],
                st: Settings) -> tuple[Reason, ...]:
    """Записи PLAN_EQUALS_FACT: тогда и только тогда, когда предикат истинен (6.2)."""
    out = []
    for card in cards:
        if not card.plan_equals_fact_applied:
            continue
        _, policy = resolve_plan_equals_fact(days[card.day], st)
        out.append(Reason(STEP_CARDS, PLAN_EQUALS_FACT, {
            "day": card.day, "plan_before": plan_of_day(days[card.day], st),
            "plan_after": card.plan_minutes, "policy": policy}))
    return tuple(out)


def build_trace(stage_records: StageRecords, cards: Sequence[DayCard],
                days: Mapping[dt.date, Day], st: Settings) -> tuple[Reason, ...]:
    return (*stage_records.opening,
            *pef_reasons(cards, days, st),
            *stage_records.credit_unpaid,
            *stage_records.placement,
            *stage_records.bank,
            *stage_records.cascade,
            *stage_records.replacement,
            *stage_records.closing)
