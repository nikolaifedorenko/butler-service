from typing import Sequence

from ..settings.types import Settings
from ..types.entities import Day, Interval
from .classify_overtime import classify_overtime
from .weight_of_day import weight_of_day


def codes_of_day(day: Day, parts: Sequence[Interval], st: Settings) -> dict[str, int]:
    """Категории → коды УТ с учётом веса дня."""
    weight = weight_of_day(day, st)
    tariff = {c.name: c.tariffs[weight] for c in st.categories}
    return {tariff[name]: m for name, m in classify_overtime(parts, st).items() if m > 0}
