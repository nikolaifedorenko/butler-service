from typing import Sequence

from ..codes_registry.flag_codes import MISSED_DAY
from ..types.entities import Interval
from ..types.results import DayCard, Flag


def missed_flag(subs: Sequence[Interval], intervals: Sequence[Interval], card: DayCard | None,
                now_minute: int) -> Flag | None:
    """Р22: подинтервалы завершились без исходного присутствия, План=Факт не применён."""
    if not subs or now_minute < subs[-1].end_minute or (card and card.plan_equals_fact_applied):
        return None
    if any(i.start_minute < s.end_minute and i.end_minute > s.start_minute for s in subs for i in intervals):
        return None
    return Flag(subs[0].day, MISSED_DAY, {"shift_segments": tuple((s.start_minute, s.end_minute) for s in subs),
                                          "absence_covered": False})
