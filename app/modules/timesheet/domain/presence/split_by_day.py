"""split_by_day(sessions, period, st) — нарезка сессий локальными полуночами на дневные
куски (день, начало, конец); куски нулевой длины отбрасываются (4.3, EX-48, EX-50).
«Ушёл ровно в 00:00» — кусок нового дня нулевой (следствие нарезки, не отдельное правило)."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from ..settings.types import Settings
from ..time.local_midnight import local_midnight, next_midnight
from ..types.entities import Period, Session

Piece = tuple[dt.date, dt.datetime, dt.datetime]


def _pieces_of_day(session: Session, day: dt.date, st: Settings) -> Piece | None:
    lo, hi = local_midnight(day, st.tz), next_midnight(day, st.tz)
    end = session.end if session.end is not None else hi
    start, stop = max(session.start, lo), min(end, hi)
    return (day, start, stop) if start < stop else None


def split_by_day(sessions: Sequence[Session], period: Period,
                 st: Settings) -> tuple[Piece, ...]:
    days = (period.start + dt.timedelta(days=i)
            for i in range((period.end - period.start).days + 1))
    pieces = ((day, session) for day in days for session in sessions)
    return tuple(p for p in (_pieces_of_day(s, d, st) for d, s in pieces) if p is not None)
