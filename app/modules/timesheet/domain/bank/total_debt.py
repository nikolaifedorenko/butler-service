"""total_debt(cards, available) — T = Σ дневных недостач + max(0, −A): отрицательная
часть банка входит в долг ровно один раз (4.8)."""
from __future__ import annotations

from typing import Sequence

from ..types.results import DayCard


def total_debt(cards: Sequence[DayCard], available_bank: int) -> int:
    return sum(c.debt_minutes for c in cards) + max(0, -available_bank)
