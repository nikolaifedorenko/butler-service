"""presence_intervals — расчётный путь (4.3, 4.5, 6.3 стадия 4): сопряжение округлённых
отметок в исходном порядке → обрезка по горизонту H → нарезка по дням → Interval (на сетке)."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from ..sessions.pair_marks import pair_marks
from ..settings.types import Settings
from ..time.calc_horizon import calc_horizon
from ..time.local_minute import local_minute
from ..types.entities import CalcMark, Interval, Period
from .split_by_day import split_by_day


def presence_intervals(period: Period, calc_marks: Sequence[CalcMark],
                       opening_mark: CalcMark | None, now_calc: dt.datetime,
                       st: Settings) -> Mapping[dt.date, tuple[Interval, ...]]:
    horizon = calc_horizon(period, now_calc, st)
    sessions = pair_marks(calc_marks, opening_mark, horizon=horizon)
    out: dict[dt.date, list[Interval]] = {}
    for day, start, end in split_by_day(sessions, period, st):
        out.setdefault(day, []).append(
            Interval(day, local_minute(start, day, st), local_minute(end, day, st)))
    return {day: tuple(items) for day, items in out.items()}
