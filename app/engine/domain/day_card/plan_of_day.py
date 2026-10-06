from ..settings.types import Settings
from ..types.entities import Day
from .policy_of import policy_of


def plan_of_day(day: Day, st: Settings) -> int:
    """Р6: план = часы Табеля; для кодов без часов — 0."""
    return day.plan_minutes if policy_of(day, st).carries_hours else 0
