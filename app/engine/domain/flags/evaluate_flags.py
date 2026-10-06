import datetime as dt
from typing import Sequence

from ..checks.check_raw_sessions import check_raw_sessions
from ..checks.check_segments import check_segments
from ..presence.end_minute_of_day import end_minute_of_day
from ..presence.marks_of_day import marks_of_day
from ..presence.presence_intervals import presence_intervals
from ..presence.sort_marks import sort_marks
from ..settings.types import Settings
from ..time.to_calc_mark import to_calc_mark
from ..time.to_raw_mark import to_raw_mark
from ..time.today_of import today_of
from ..types.entities import Absence, Day, KIND_IN, Mark, Period, Shift
from ..types.results import DayCard, FlagsResult
from .day_flags import day_flags
from .merge_absences import merge_absences
from .session_open import session_open_flag
from .shift_segments import shift_segments


def _period_days(period: Period) -> list[dt.date]:
    return [period.start + dt.timedelta(days=i) for i in range((period.end - period.start).days + 1)]


def _open_since(raw: Sequence, today: dt.date, period: Period):
    if today < period.start or not raw or raw[-1].source.kind != KIND_IN:
        return None, None
    return min(today, period.end), raw[-1].source.at_utc


def evaluate_flags(period: Period, days: Sequence[Day], cards: Sequence[DayCard], marks: Sequence[Mark],
                   opening_mark: Mark | None, shifts: Sequence[Shift], absences: Sequence[Absence],
                   st: Settings, now: dt.datetime) -> FlagsResult:
    """Конвейер флагов: исходные отметки, исходный now, График. Ни одного числа не меняет."""
    source = ([opening_mark] if opening_mark else []) + list(marks)
    raw = sort_marks([to_raw_mark(m, st) for m in source])
    calc = sort_marks([to_calc_mark(m, st) for m in marks])
    today = today_of(now, st.tz)
    presence = presence_intervals(_period_days(period), raw, now, today, st.tz)
    check_raw_sessions(presence.intervals)
    segments = shift_segments(shifts, st.tz)
    check_segments(segments)
    gaps, by_card = merge_absences(absences), {c.day: c for c in cards}
    flags = [f for d in days for f in day_flags(
        d, by_card.get(d.day), presence.intervals.get(d.day, ()), segments, gaps, marks_of_day(calc, d.day),
        end_minute_of_day(d.day, today, now, st.tz), st)]
    flag_day, since = _open_since(raw, today, period)
    extra = session_open_flag(flag_day, since) if flag_day else None
    return FlagsResult(tuple(flags + ([extra] if extra else [])))
