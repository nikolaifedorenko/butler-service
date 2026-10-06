from ..settings.resolve_modifier import resolve_modifier
from ..settings.types import MOD_DOUBLE, Settings
from ..types.entities import Day


def weight_of_day(day: Day, st: Settings) -> int:
    """Р11: при «Двойные переработки = Да» вес часа переработки — double_weight, иначе 1."""
    double = resolve_modifier(MOD_DOUBLE, day.employee_id, day.group, day.day, st, False)
    return st.double_weight if double else 1
