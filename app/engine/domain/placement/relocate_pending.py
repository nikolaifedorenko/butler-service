import datetime as dt
from typing import Mapping, Sequence

from ..codes_registry.reason_codes import PASS_AFTER_CASCADE
from ..settings.types import Settings
from ..types.entities import Day
from ..types.results import DayCard, Reason
from .codes import Codes
from .relocate_codes import relocate_codes


def relocate_pending(cards: Sequence[DayCard], days: Mapping[dt.date, Day], codes: Codes,
                     st: Settings) -> tuple[Reason, ...]:
    """Стадия 12: тот же алгоритм для оставшихся неразмещённых блоков после каскада."""
    return relocate_codes(cards, days, codes, st, PASS_AFTER_CASCADE)
