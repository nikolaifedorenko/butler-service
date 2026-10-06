from ..settings.resolve_modifier import resolve_modifier
from ..settings.types import MOD_COUNTS_IN_UT, Settings
from ..types.entities import Day
from .policy_of import policy_of


def counts_in_ut(day: Day, st: Settings) -> bool:
    """Т4 «Учитываются ли часы в УТ» по приоритету, иначе Т1 «Учитывается в УТ»."""
    default = policy_of(day, st).counts_in_ut
    return bool(resolve_modifier(MOD_COUNTS_IN_UT, day.employee_id, day.group, day.day, st, default))
