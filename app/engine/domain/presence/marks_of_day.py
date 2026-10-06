import datetime as dt
from typing import Sequence

from ..types.entities import CalcMark


def marks_of_day(marks: Sequence[CalcMark], day: dt.date) -> tuple[CalcMark, ...]:
    """Отметки дня в порядке момента (при равенстве — в порядке источника)."""
    return tuple(m for m in marks if m.day == day)
