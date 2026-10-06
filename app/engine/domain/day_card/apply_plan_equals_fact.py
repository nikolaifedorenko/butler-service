from ..settings.types import Settings
from ..types.entities import Day
from .resolve_plan_equals_fact import resolve_plan_equals_fact


def apply_plan_equals_fact(day: Day, plan: int, has_presence: bool, st: Settings) -> int:
    """План := 0, если модификатор «Да» и присутствия в дне нет (Р12)."""
    return 0 if (not has_presence and resolve_plan_equals_fact(day, st)) else plan
