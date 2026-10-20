"""raw_presence_intervals — исходный путь флагов (4.5, 6.6 стадия 1): те же шаги по
исходным отметкам, обрезка по H_raw, нарезка → RawInterval с секундами. Усечение и
округление до минут запрещено (EX-49). Открытый интервал текущего дня заканчивается в now."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Sequence

from ..sessions.pair_marks import pair_marks
from ..settings.types import Settings
from ..time.calc_horizon import calc_horizon
from ..types.entities import Mark, Period, RawInterval
from .split_by_day import split_by_day


def raw_presence_intervals(period: Period, marks: Sequence[Mark], opening_mark: Mark | None,
                           now: dt.datetime,
                           st: Settings) -> Mapping[dt.date, tuple[RawInterval, ...]]:
    horizon = calc_horizon(period, now, st)          # H_raw = min(now, полночь после period.end)
    sessions = pair_marks(marks, opening_mark, horizon=horizon)
    out: dict[dt.date, list[RawInterval]] = {}
    for day, start, end in split_by_day(sessions, period, st):
        out.setdefault(day, []).append(RawInterval(day, start, end))
    return {day: tuple(items) for day, items in out.items()}
