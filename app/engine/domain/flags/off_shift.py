from typing import Sequence

from ..codes_registry.flag_codes import OFF_SHIFT_ATTENDANCE
from ..settings.types import Settings
from ..types.entities import Interval
from ..types.results import Flag
from ._moment import moment_of


def off_shift_flag(subs: Sequence[Interval], intervals: Sequence[Interval], segments: Sequence[Interval],
                   absences: Sequence[tuple[int, int]], st: Settings) -> Flag | None:
    """Ожидаемых подинтервалов нет, но исходное присутствие в дне есть."""
    if subs or not intervals:
        return None
    first = intervals[0]
    return Flag(first.day, OFF_SHIFT_ATTENDANCE, {
        "first_presence_at": moment_of(first.day, first.start_minute, st.tz),
        "shift_segments": tuple((s.start_minute, s.end_minute) for s in segments),
        "absence_intervals": tuple(absences)})
