import datetime as dt
from typing import Sequence

from ..types.entities import CLOSED, KIND_IN, OPEN, CalcMark


def state_before(marks: Sequence[CalcMark], day: dt.date) -> str:
    """Тип последней отметки, относящейся к дню раньше day; closed, если таких нет."""
    earlier = [m for m in marks if m.day < day]
    return OPEN if earlier and earlier[-1].source.kind == KIND_IN else CLOSED
