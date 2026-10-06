from typing import Sequence

from ..codes_registry.flag_codes import EARLY_DEPARTURE
from ..settings.types import Settings
from ..types.entities import Interval
from ..types.results import Flag
from ._moment import moment_of


def early_flag(sub: Interval, intervals: Sequence[Interval], now_minute: int, st: Settings) -> Flag | None:
    """EARLY_DEPARTURE: последнее присутствие в S закончилось раньше S.end − лимит и не вернулся."""
    inside = [i for i in intervals if i.start_minute < sub.end_minute and i.end_minute > sub.start_minute]
    if now_minute < sub.end_minute or not inside:
        return None
    left = min(inside[-1].end_minute, sub.end_minute)
    if left >= sub.end_minute - st.late_limit_minutes:
        return None
    return Flag(sub.day, EARLY_DEPARTURE, {"expected_at": moment_of(sub.day, sub.end_minute, st.tz),
                                           "actual_at": moment_of(sub.day, left, st.tz)})
