from ..settings.types import Settings
from ..types.entities import Day
from .hours_text import hours_text
from .policy_of import policy_of


def value_of(day: Day, st: Settings) -> str:
    """Значение Табеля: «Я 12», «В» (3.3)."""
    return f"{day.code} {hours_text(day.plan_minutes)}" if policy_of(day, st).carries_hours else day.code
