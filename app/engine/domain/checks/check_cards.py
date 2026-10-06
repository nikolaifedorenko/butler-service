from typing import Sequence

from ..codes_registry.invariant_codes import I1, I2, I3, I4, I9, I18
from ..types.results import DayCard
from ._fail import fail_if


def check_cards(cards: Sequence[DayCard], step: int) -> None:
    """И1–И4, И9, И18 для карточек дней."""
    for c in cards:
        fail_if(c.debt_minutes < 0, I1, day=c.day)
        fail_if(c.work_minutes > c.full_fact_minutes, I2, day=c.day)
        fail_if(c.work_minutes > c.plan_minutes, I3, day=c.day)
        fail_if(sum(c.codes.values()) != c.overtime_minutes, I4, day=c.day)
        fail_if(c.work_minutes + c.overtime_minutes != c.full_fact_minutes, I9, day=c.day)
        values = (c.full_fact_minutes, c.work_minutes, c.overtime_minutes, *c.codes.values())
        fail_if(any(v % step for v in values), I18, day=c.day)
