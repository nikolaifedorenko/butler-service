from typing import Mapping, Sequence

import datetime as dt

from ..day_card.receiver_ok import receiver_ok
from ..settings.types import Settings
from ..types.entities import Day
from ..types.results import DayCard
from .codes import Codes


def seed_codes(cards: Sequence[DayCard], days: Mapping[dt.date, Day], st: Settings) -> Codes:
    """Собственные коды дней; у принимающего оплачиваемого дня placed_day = source_day."""
    codes = Codes()
    for card in cards:
        placed = card.day if receiver_ok(days[card.day], st) else None
        for tariff, minutes in card.codes.items():
            codes.add(card.day, tariff, minutes, placed)
    return codes
