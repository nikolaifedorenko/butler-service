"""Аккумулятор блоков кодов УТ — единственная изменяемая структура внутри settle() (2.5)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

Key = tuple[dt.date, str, "dt.date | None"]


@dataclass(frozen=True)
class CodeBlock:
    source_day: dt.date
    tariff: str
    placed_day: dt.date | None
    minutes: int


class Codes:
    """Блоки: source_day, tariff, placed_day | None, физические минуты.

    Блоки с разными source_day не объединяются; агрегация по placed_day — только в УТ.
    """

    def __init__(self) -> None:
        self._m: dict[Key, int] = {}

    def add(self, source_day: dt.date, tariff: str, minutes: int, placed_day: dt.date | None) -> None:
        key = (source_day, tariff, placed_day)
        self._m[key] = self._m.get(key, 0) + minutes

    def get(self, source_day: dt.date, tariff: str, placed_day: dt.date | None) -> int:
        return self._m.get((source_day, tariff, placed_day), 0)

    def take(self, source_day: dt.date, tariff: str, placed_day: dt.date | None, minutes: int) -> None:
        key = (source_day, tariff, placed_day)
        left = self._m.get(key, 0) - minutes
        if left < 0:
            raise ValueError("take больше остатка блока")
        self._m[key] = left

    def place(self, source_day: dt.date, tariff: str, placed_day: dt.date, minutes: int) -> None:
        self.take(source_day, tariff, None, minutes)
        self.add(source_day, tariff, minutes, placed_day)

    def blocks(self) -> tuple[CodeBlock, ...]:
        return tuple(CodeBlock(s, t, p, m) for (s, t, p), m in self._m.items() if m > 0)

    def placed_total(self, day: dt.date) -> int:
        return sum(m for (_, _, p), m in self._m.items() if p == day)

    def total(self) -> int:
        return sum(self._m.values())
