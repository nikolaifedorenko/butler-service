"""Модель половинок суток — ядро шахматки (PoC SPEC §5, перенос без изменений).

Каждая дата делится на AM (до выезда) и PM (с заезда); позиция на общей шкале —
ordinal*2 + half. Занятость — отрезок [start_pos, end_pos] с включёнными границами:
выезд утром и заезд днём в один объект в тот же день не пересекаются.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Sequence

AM = 0
PM = 1


def pos(day: dt.date, half: int) -> int:
    return day.toordinal() * 2 + half


def overlaps(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 <= b1 and b0 <= a1


def hold_span(start: dt.date, end: dt.date) -> tuple[int, int]:
    """Блок/OOO занимает целые сутки с–по."""
    return pos(start, AM), pos(end, PM)


@dataclass(frozen=True)
class Segment:
    index: int
    category_id: int
    start: dt.date
    end: dt.date
    start_pos: int
    end_pos: int


def segments(check_in: dt.date, check_out: dt.date, early: bool, late: bool, category_id: int,
             moves: Sequence[tuple[dt.date, int]]) -> list[Segment]:
    """Бронь → сегменты по переездам (PoC §5.3): РЗ расширяет первый сегмент, ПВ —
    последний; в день переезда утро в старом объекте, вечер в новом."""
    ordered = sorted(moves)
    bounds = [check_in, *(d for d, _ in ordered), check_out]
    cats = [category_id, *(c for _, c in ordered)]
    last = len(cats) - 1
    return [Segment(i, cats[i], bounds[i], bounds[i + 1],
                    pos(bounds[i], AM if i == 0 and early else PM),
                    pos(bounds[i + 1], PM if i == last and late else AM))
            for i in range(len(cats))]


def validate_dates(check_in: dt.date, check_out: dt.date,
                   move_dates: Sequence[dt.date]) -> list[str]:
    """Инварианты PoC §5.3: бронь и каждый сегмент — не короче одной ночи."""
    if check_out <= check_in:
        return ["Выезд должен быть позже заезда"]
    if any(not check_in < d < check_out for d in move_dates):
        return ["Дата переезда вне проживания"]
    if len(set(move_dates)) != len(move_dates):
        return ["Две даты переезда совпадают"]
    return []


def segment_on(segs: Sequence[Segment], day: dt.date, half: int) -> Segment | None:
    """Сегмент, который занимает объект в эту половину суток (или None)."""
    p = pos(day, half)
    return next((s for s in segs if s.start_pos <= p <= s.end_pos), None)
