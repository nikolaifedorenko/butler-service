from ..settings.types import DayCodePolicy, Settings
from ..types.entities import Day
from ..types.errors import UnknownDayCodeError


def policy_of(day: Day, st: Settings) -> DayCodePolicy:
    """Строка Т1 для кода дня."""
    if day.code not in st.day_codes:
        raise UnknownDayCodeError(day.code, day.day)
    return st.day_codes[day.code]
