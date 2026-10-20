"""debt_of_day(day, work, applied, st) — недостача дня (v7/R15, RUL-DEBT-FORMULA):
applied ⇒ 0 (освобождение «План=Факт»); окна нет ⇒ 0; иначе max(0, длина окна − work).
План строки Табеля в расчёте долга не участвует; недостача всегда кратна шагу."""
from __future__ import annotations

from ..settings.types import Settings
from ..types.entities import Day, Minutes
from .window_of_day import window_of_day


def debt_of_day(day: Day, work: Minutes, applied: bool, st: Settings) -> Minutes:
    if applied:
        return 0
    window = window_of_day(day, st)
    return 0 if window is None else max(0, window.length - work)
