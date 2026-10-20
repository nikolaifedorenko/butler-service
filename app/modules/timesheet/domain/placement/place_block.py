"""place_block(block, cards, days, codes, st, pass_) — размещение одного блока
(6.3, стадия 8, шаг 4): ближайшие допустимые приёмники строго после source_day;
дни с receiver_ok = Нет пропускаются (RUL-SKIP-NON-RECEIVER); частичное размещение —
остаток идёт к следующему кандидату; неразмещённый остаток остаётся в Codes."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from ..codes_registry.reason_codes import (
    CODE_PLACED,
    PASS_PRIMARY,
    STEP_PLACEMENT,
    STEP_REPLACEMENT,
)
from ..day_card.receiver_ok import receiver_ok
from ..settings.types import Settings
from ..types.entities import Day
from ..types.results import DayCard, Reason
from .candidate_days import candidate_days
from .codes import CodeBlock, Codes
from .free_capacity import free_capacity


def _reason(block: CodeBlock, day: dt.date, minutes: int, pass_: str) -> Reason:
    step = STEP_PLACEMENT if pass_ == PASS_PRIMARY else STEP_REPLACEMENT
    return Reason(step, CODE_PLACED, {"source_day": block.source_day, "placed_day": day,
                                      "tariff": block.tariff, "minutes": minutes, "pass": pass_})


def place_block(block: CodeBlock, cards: Sequence[DayCard], days: Mapping[dt.date, Day],
                codes: Codes, st: Settings, pass_: str) -> tuple[Reason, ...]:
    remaining, reasons = block.minutes, []
    for card in candidate_days(cards, block.source_day):
        put = min(remaining, free_capacity(card, codes, st)) if receiver_ok(days[card.day], st) else 0
        if put > 0:
            codes.place(block.source_day, block.tariff, card.day, put)
            remaining -= put
            reasons.append(_reason(block, card.day, put, pass_))
    return tuple(reasons)
