import datetime as dt
from typing import Sequence

from ..types.entities import KIND_IN, CalcMark


def open_session_since(marks: Sequence[CalcMark], last_day: dt.date) -> dt.datetime | None:
    """Исходный момент последнего «пришёл», если к концу last_day сессия открыта."""
    upto = [m for m in marks if m.day <= last_day]
    return upto[-1].source.at_utc if upto and upto[-1].source.kind == KIND_IN else None
