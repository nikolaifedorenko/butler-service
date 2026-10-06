from ..settings.types import Settings, Window
from ..types.entities import Day
from ..types.errors import ConfigError
from .policy_of import policy_of
from .value_of import value_of


def window_of_day(day: Day, st: Settings) -> Window | None:
    """Окно Т2 по значению Табеля; для значений без часов окна нет (В1 — ConfigError)."""
    if not policy_of(day, st).carries_hours:
        return None
    value = value_of(day, st)
    if value not in st.windows:
        raise ConfigError([("V1", {"value": value, "day": day.day})])
    return st.windows[value]
