from ..settings.resolve_modifier import resolve_modifier
from ..settings.types import MOD_PAYS, Settings
from ..types.entities import Day
from .counts_in_ut import counts_in_ut


def pays_overtime(day: Day, st: Settings) -> bool:
    """5.2: counts_in_ut(D) И Т4 «Оплачиваются ли переработки»(D)."""
    pays = resolve_modifier(MOD_PAYS, day.employee_id, day.group, day.day, st, True)
    return counts_in_ut(day, st) and bool(pays)
