"""expected_subintervals(segments, absences, day) — ожидаемые подинтервалы дня:
отрезки смены минус (отсутствие ∩ отрезок) (4.7, 6.6 стадия 4). Не осталось —
сотрудник в этот день не ожидается."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from .shift_segments import Segment


def _subtract(piece: Segment, absence: Segment) -> list[Segment]:
    (start, end), (a, b) = piece, absence
    out = []
    if a > start:
        out.append((start, min(end, a)))
    if b < end:
        out.append((max(start, b), end))
    return [p for p in out if p[0] < p[1]]


def expected_subintervals(segments: Sequence[Segment], absences: Sequence[Segment],
                          day: dt.date) -> tuple[Segment, ...]:
    pieces = list(segments)
    for absence in absences:
        pieces = [p for piece in pieces for p in _subtract(piece, absence)]
    return tuple(sorted(pieces))
