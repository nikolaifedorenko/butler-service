from typing import Sequence

from ..settings.types import Settings
from ..types.entities import Day
from ..types.errors import UnknownDayCodeError


def check_known_day_codes(days: Sequence[Day], st: Settings) -> None:
    """Стадия 1: каждый код дня есть в Т1."""
    unknown = next((d for d in days if d.code not in st.day_codes), None)
    if unknown:
        raise UnknownDayCodeError(unknown.code, unknown.day)
