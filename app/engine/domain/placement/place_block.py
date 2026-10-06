import datetime as dt
from typing import Mapping, Sequence

from ..codes_registry.reason_codes import CODE_PLACED
from ..day_card.receiver_ok import receiver_ok
from ..settings.types import Settings
from ..types.entities import Day
from ..types.results import DayCard, Reason
from .candidate_days import candidate_days
from .codes import CodeBlock, Codes
from .free_capacity import free_capacity


def place_block(block: CodeBlock, cards: Sequence[DayCard], days: Mapping[dt.date, Day],
                codes: Codes, st: Settings, pass_: str) -> tuple[Reason, ...]:
    """Ближайший допустимый приёмник вперёд; частичное размещение; остаток ждёт дальше."""
    remaining, reasons = block.minutes, []
    for card in candidate_days(cards, block.source_day):
        put = min(remaining, free_capacity(card, codes, st)) if receiver_ok(days[card.day], st) else 0
        if put > 0:
            codes.place(block.source_day, block.tariff, card.day, put)
            remaining -= put
            reasons.append(Reason("placement", CODE_PLACED, {
                "source_day": block.source_day, "placed_day": card.day, "tariff": block.tariff,
                "minutes": put, "pass": pass_}))
    return tuple(reasons)
