from typing import Sequence

from ..day_card.build_day_card import build_day_card
from ..presence.marks_of_day import marks_of_day
from ..presence.presence_intervals import Presence
from ..settings.types import Settings
from ..types.entities import CalcMark, Day
from ..types.results import DayCard


def build_cards(days: Sequence[Day], presence: Presence, marks: Sequence[CalcMark],
                st: Settings) -> tuple[DayCard, ...]:
    """Стадия 5 по всем дням Табеля периода (по возрастанию дня)."""
    return tuple(build_day_card(d, presence.intervals.get(d.day, ()), marks_of_day(marks, d.day),
                                presence.open_at_start.get(d.day, False),
                                presence.open_at_end.get(d.day, False), st)
                 for d in sorted(days, key=lambda x: x.day))
