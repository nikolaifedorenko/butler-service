import datetime as dt
from typing import Sequence

from ..types.results import DayCard


def candidate_days(cards: Sequence[DayCard], after: dt.date) -> tuple[DayCard, ...]:
    """Дни периода строго после after, по возрастанию."""
    return tuple(sorted((c for c in cards if c.day > after), key=lambda c: c.day))
