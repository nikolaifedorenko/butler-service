from ..settings.types import Settings
from ..types.entities import Day
from .accepts_ut import accepts_ut
from .pays_overtime import pays_overtime


def receiver_ok(day: Day, st: Settings) -> bool:
    """5.2: допустимый приёмник = accepts_ut И pays_overtime."""
    return accepts_ut(day, st) and pays_overtime(day, st)
