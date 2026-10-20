"""evaluate_flags — композиция периода (6.6): исходные интервалы (обрезка по H_raw) →
отрезки смен (слияние смежных, вне периода отбрасываются) → слияние отсутствий →
ожидаемые подинтервалы → флаги дня → канонический порядок (3.4).

Работает на исходных отметках и исходном now, без округления (4.5). Из часового
конвейера — только plan_equals_fact: Mapping[date, bool] (R30; карточки, банк, коды
и долг флаги не получают — 13 п.5)."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from ..checks.check_cards import check_pef_coverage
from ..checks.check_raw_intervals import check_raw_intervals
from ..checks.check_segments import check_segments
from ..codes_registry.flag_codes import ALL as FLAG_ORDER
from ..presence.raw_presence_intervals import raw_presence_intervals
from ..schedule.expected_subintervals import expected_subintervals
from ..schedule.merge_absences import merge_absences
from ..schedule.shift_segments import Segment, shift_segments
from ..settings.types import Settings
from ..time.local_midnight import local_midnight, next_midnight
from ..types.entities import Absence, Day, Mark, Period, Shift
from ..types.results import Flag, FlagsResult
from .day_flags import day_flags


def _in_period(segments: Mapping[dt.date, tuple[Segment, ...]],
               period: Period) -> Mapping[dt.date, tuple[Segment, ...]]:
    return {d: s for d, s in segments.items() if period.start <= d <= period.end}


def _day_absences(day: dt.date, merged: Sequence[Segment],
                  st: Settings) -> tuple[Segment, ...]:
    lo, hi = local_midnight(day, st.tz), next_midnight(day, st.tz)
    return tuple(a for a in merged if a[0] < hi and a[1] > lo)


def evaluate_flags(period: Period, days: Sequence[Day], plan_equals_fact: Mapping[dt.date, bool],
                   marks: Sequence[Mark], opening_mark: Mark | None, shifts: Sequence[Shift],
                   absences: Sequence[Absence], st: Settings, now: dt.datetime) -> FlagsResult:
    check_pef_coverage(period, days, plan_equals_fact)
    raw = raw_presence_intervals(period, marks, opening_mark, now, st)
    check_raw_intervals(raw, st)
    segments = _in_period(shift_segments(shifts, st), period)
    check_segments(segments, st)
    merged = merge_absences(absences)
    collected: list[Flag] = []
    for day in sorted(days, key=lambda d: d.day):
        segs = segments.get(day.day, ())
        day_abs = _day_absences(day.day, merged, st)
        subs = expected_subintervals(segs, day_abs, day.day)
        collected.extend(day_flags(day, subs, raw.get(day.day, ()), segs, day_abs,
                                   plan_equals_fact[day.day], now, st))
    order = {code: i for i, code in enumerate(FLAG_ORDER)}
    return FlagsResult(tuple(sorted(collected, key=_canonical(order))))


def _canonical(order: Mapping[str, int]):
    """Канонический порядок FlagsResult (3.4): день, порядок кодов реестра 6.6,
    возрастание временного ключа."""
    def key(flag: Flag):
        return (flag.day, order[flag.code],
                flag.data.get("expected_at") or flag.data.get("first_presence_at"))
    return key
