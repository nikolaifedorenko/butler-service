"""candidate_days(cards, after) — дни периода строго после source_day, по возрастанию
(6.3, стадия 8; перенос только вперёд — RUL-PLACEMENT-FORWARD)."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from ..types.results import DayCard


def candidate_days(cards: Sequence[DayCard], after: dt.date) -> tuple[DayCard, ...]:
    return tuple(c for c in cards if c.day > after)
