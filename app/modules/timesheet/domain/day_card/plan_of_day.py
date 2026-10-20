"""plan_of_day(day, st) — план карточки = длина окна значения; 0, если окна нет
(v7.1/R34, RUL-PLAN-FROM-WINDOW). Day.plan_minutes — информационный план строки."""
from __future__ import annotations

from ..settings.types import Settings
from ..types.entities import Day, Minutes
from .window_of_day import window_of_day


def plan_of_day(day: Day, st: Settings) -> Minutes:
    window = window_of_day(day, st)
    return window.length if window is not None else 0
