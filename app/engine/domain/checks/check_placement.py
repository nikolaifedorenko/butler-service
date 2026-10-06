import datetime as dt
from typing import Mapping, Sequence

from ..codes_registry.invariant_codes import I6, I7, I19
from ..day_card.accepts_ut import accepts_ut
from ..day_card.receiver_ok import receiver_ok
from ..placement.codes import Codes
from ..settings.types import Settings
from ..types.entities import Day
from ..types.results import DayCard
from ._fail import fail_if


def check_placement(cards: Sequence[DayCard], days: Mapping[dt.date, Day], codes: Codes,
                    st: Settings) -> None:
    """И6 лимит дня; И7 нет кодов в неприёмных днях; И19 переносы только вперёд в приёмник."""
    for c in cards:
        fail_if(c.plan_minutes + codes.placed_total(c.day) > st.day_limit_minutes, I6, day=c.day)
        ok = accepts_ut(days[c.day], st) and c.pays_overtime
        fail_if(not ok and codes.placed_total(c.day) > 0, I7, day=c.day)
    for b in (b for b in codes.blocks() if b.placed_day and b.placed_day != b.source_day):
        fail_if(b.placed_day < b.source_day or not receiver_ok(days[b.placed_day], st), I19, block=b)
