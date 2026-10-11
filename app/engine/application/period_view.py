"""PeriodView и day_views (7.1, 3.2): склейка SettleResult/FlagsResult со строками
Табеля и интервалом трудоустройства; DayView.timesheet_plan_minutes — информационный
план строки (v7.1/R39)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Mapping, Sequence

from ..domain.types.entities import Day, Employment
from ..domain.types.results import DayView, Flag, FlagsResult, SettleResult


@dataclass(frozen=True)
class PeriodView:
    settle: SettleResult
    flags: FlagsResult
    employment: Employment            # источник отображения дней «не в штате» (16.6, v7.1)
    days: tuple[Day, ...]             # строки Табеля запрошенного периода (R39)


def _flags_by_day(flags: FlagsResult) -> Mapping[dt.date, tuple[Flag, ...]]:
    out: dict[dt.date, list[Flag]] = {}
    for flag in flags.flags:
        out.setdefault(flag.day, []).append(flag)
    return {day: tuple(items) for day, items in out.items()}


def day_views(view: PeriodView) -> Sequence[DayView]:
    by_day = _flags_by_day(view.flags)
    plans = {row.day: row.plan_minutes for row in view.days}
    return tuple(DayView(card, by_day.get(card.day, ()), plans.get(card.day, 0))
                 for card in view.settle.cards)
