from ..settings.types import Settings
from ..types.entities import Day
from .policy_of import policy_of


def accepts_ut(day: Day, st: Settings) -> bool:
    """5.2: Т1 «Принимает коды УТ»."""
    return policy_of(day, st).accepts_ut
