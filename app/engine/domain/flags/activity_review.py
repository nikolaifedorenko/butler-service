from typing import Sequence

from ..codes_registry.flag_codes import ACTIVITY_REQUIRES_REVIEW
from ..day_card.policy_of import policy_of
from ..settings.types import Settings
from ..types.entities import CalcMark, Day
from ..types.results import Flag


def activity_review_flags(day: Day, calc_marks: Sequence[CalcMark], st: Settings) -> tuple[Flag, ...]:
    """Каждая реальная отметка (расчётного) дня с «Активность требует проверки = Да»."""
    if not policy_of(day, st).activity_requires_review:
        return ()
    return tuple(Flag(day.day, ACTIVITY_REQUIRES_REVIEW, {
        "day_code": day.code, "kind": m.source.kind, "at_utc": m.source.at_utc}) for m in calc_marks)
