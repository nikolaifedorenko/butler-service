"""INV-DAY-LIMIT, INV-NO-CODES-WHEN-EXCLUDED, INV-PLACEMENT-FORWARD
(10.1: после стадии 8 и после стадии 12)."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from ..codes_registry.invariant_codes import (
    INV_DAY_LIMIT,
    INV_NO_CODES_WHEN_EXCLUDED,
    INV_PLACEMENT_FORWARD,
)
from ..day_card.receiver_ok import receiver_ok
from ..placement.codes import Codes
from ..settings.types import Settings
from ..types.entities import Day
from ..types.results import DayCard
from ._fail import fail


def _check_day_limit(card: DayCard, codes: Codes, st: Settings) -> None:
    total = card.plan_minutes + codes.placed_total(card.day)
    if total > st.day_limit_minutes:
        fail(INV_DAY_LIMIT, {"day": card.day, "plan": card.plan_minutes, "placed": total})


def _check_excluded(card: DayCard, day: Day, codes: Codes, st: Settings) -> None:
    excluded = not receiver_ok(day, st)
    if excluded and codes.placed_total(card.day) > 0:
        fail(INV_NO_CODES_WHEN_EXCLUDED, {"day": card.day})


def _check_forward(codes: Codes, days: Mapping[dt.date, Day], st: Settings) -> None:
    for b in codes.blocks():
        if b.placed_day is None or b.placed_day == b.source_day:
            continue
        if b.placed_day <= b.source_day or not receiver_ok(days[b.placed_day], st):
            fail(INV_PLACEMENT_FORWARD, {"source_day": b.source_day, "placed_day": b.placed_day,
                                         "tariff": b.tariff})


def check_placement(cards: Sequence[DayCard], days: Mapping[dt.date, Day], codes: Codes,
                    st: Settings) -> None:
    for card in cards:
        _check_day_limit(card, codes, st)
        _check_excluded(card, days[card.day], codes, st)
    _check_forward(codes, days, st)
