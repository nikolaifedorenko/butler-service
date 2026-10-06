from typing import Sequence

from ..codes_registry.flag_codes import LATE
from ..settings.types import Settings
from ..types.entities import Interval
from ..types.results import Flag
from ._moment import moment_of
from .present_at import present_at


def late_flag(sub: Interval, intervals: Sequence[Interval], now_minute: int, st: Settings) -> Flag | None:
    """LATE: в S.start не присутствовал, первый приход в S позже S.start + лимит (или ещё не пришёл)."""
    deadline = sub.start_minute + st.late_limit_minutes
    if now_minute < deadline or present_at(intervals, sub.start_minute):
        return None
    arrival = next((i.start_minute for i in intervals if sub.start_minute <= i.start_minute < sub.end_minute), None)
    if (arrival is None and now_minute >= sub.end_minute) or (arrival is not None and arrival <= deadline):
        return None
    actual = moment_of(sub.day, arrival, st.tz) if arrival is not None else None
    return Flag(sub.day, LATE, {"expected_at": moment_of(sub.day, sub.start_minute, st.tz), "actual_at": actual})
