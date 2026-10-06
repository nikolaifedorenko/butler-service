"""«Кто на работе»: текущее присутствие и ожидания по Графику на сегодня.

Запрос строится из тех же доменных функций, что и evaluate_flags(): исходные интервалы
присутствия (4.3, без округления), отрезки смен (Р31) и согласованные отсутствия (5.1).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Sequence

from ..domain.flags.expected_subintervals import expected_subintervals
from ..domain.flags.merge_absences import merge_absences
from ..domain.flags.shift_segments import shift_segments
from ..domain.presence.presence_intervals import presence_intervals
from ..domain.presence.sort_marks import sort_marks
from ..domain.time.local_midnight import local_midnight
from ..domain.time.local_minute import local_minute
from ..domain.time.to_raw_mark import to_raw_mark
from ..domain.time.today_of import today_of
from ..domain.types.entities import KIND_IN, Interval, Period
from .context import EnginePorts
from .periods import month_period

PRESENT, STEPPED_OUT, EXPECTED, NONE = "present", "stepped_out", "expected", "none"


@dataclass(frozen=True)
class PresenceRow:
    employee_id: str
    status: str
    since: dt.datetime | None           # приход открытой сессии (исходный момент)
    expected_at: dt.datetime | None     # ожидаемый приход / возвращение
    expected_until: dt.datetime | None  # конец текущего ожидаемого отрезка
    overdue: bool                       # ожидаемое время уже прошло (с учётом лимита опоздания)
    planned_today: bool
    left_at: dt.datetime | None         # когда ушёл (для «отлучился»)
    subintervals: tuple[tuple[int, int], ...]


def _row(eid: str, ports: EnginePorts, now: dt.datetime, st) -> PresenceRow:
    today = today_of(now, st.tz)
    span = Period(today - dt.timedelta(days=1), today)
    lo = local_midnight(span.start, st.tz)
    raw = sort_marks([to_raw_mark(m, st) for m in ports.punch.marks_between(eid, lo, now) if m.at_utc <= now])
    opening = ports.punch.last_mark_before(eid, lo)
    marks = ([to_raw_mark(opening, st)] if opening else []) + list(raw)
    presence = presence_intervals([span.start, today], marks, now, today, st.tz)
    segments = shift_segments(ports.shift.shifts(eid, span), st.tz)
    subs = expected_subintervals(segments, merge_absences(ports.absence.absences(eid, span)), today)
    return classify(eid, marks, presence.intervals.get(today, ()), subs, now, today, st)


def classify(eid, marks, today_intervals: Sequence[Interval], subs: Sequence[Interval], now, today, st):
    minute = local_minute(now, today, st.tz)
    remaining = [s for s in subs if s.end_minute > minute]
    at = lambda m: local_midnight(today, st.tz) + dt.timedelta(minutes=m)  # noqa: E731
    present = bool(marks) and marks[-1].source.kind == KIND_IN
    nxt = remaining[0] if remaining else None
    status = PRESENT if present else (STEPPED_OUT if nxt and today_intervals else (EXPECTED if nxt else NONE))
    overdue = bool(nxt) and not present and nxt.start_minute + st.late_limit_minutes < minute
    left = at(today_intervals[-1].end_minute) if (status == STEPPED_OUT) else None
    return PresenceRow(eid, status, marks[-1].source.at_utc if present else None,
                       at(nxt.start_minute) if nxt else None, at(nxt.end_minute) if nxt else None,
                       overdue, bool(subs), left, tuple((s.start_minute, s.end_minute) for s in subs))


def presence_board(employee_ids: Sequence[str], ports: EnginePorts) -> tuple[PresenceRow, ...]:
    now = ports.clock.now()
    st = ports.settings.load(month_period(now.year, now.month))
    return tuple(_row(eid, ports, now, st) for eid in employee_ids)
