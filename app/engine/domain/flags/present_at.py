from typing import Sequence

from ..types.entities import Interval


def present_at(intervals: Sequence[Interval], minute: int) -> bool:
    """Присутствует ли сотрудник в минуту дня."""
    return any(i.start_minute <= minute < i.end_minute for i in intervals)
