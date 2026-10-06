from typing import Sequence

from ..types.results import DayCard


def total_debt(cards: Sequence[DayCard], available: int) -> int:
    """Σ недостач + отрицательная часть доступного банка (ровно один раз)."""
    return sum(c.debt_minutes for c in cards) + max(0, -available)
