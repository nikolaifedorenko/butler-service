import datetime as dt
from typing import Mapping, Sequence

from ..codes_registry.reason_codes import PLAN_EQUALS_FACT
from ..day_card.plan_of_day import plan_of_day
from ..settings.types import Settings
from ..types.entities import Day
from ..types.results import DayCard, Reason


def pef_reasons(cards: Sequence[DayCard], days: Mapping[dt.date, Day], st: Settings) -> tuple[Reason, ...]:
    """PLAN_EQUALS_FACT для дней, где модификатор применён."""
    return tuple(Reason("cards", PLAN_EQUALS_FACT, {
        "day": c.day, "plan_before": plan_of_day(days[c.day], st), "plan_after": c.plan_minutes,
        "policy": "plan_equals_fact"}) for c in cards if c.plan_equals_fact_applied)
