from typing import Sequence

from ..types.entities import Interval


def subtract_segments(interval: Interval, segments: Sequence[tuple[int, int]]) -> tuple[Interval, ...]:
    """Части интервала вне заданных отрезков (отрезки не пересекаются)."""
    parts, cursor = [], interval.start_minute
    for a, b in sorted(segments):
        if b > cursor and a < interval.end_minute:
            parts.append((cursor, min(a, interval.end_minute)))
            cursor = max(cursor, b)
    parts.append((cursor, interval.end_minute))
    return tuple(Interval(interval.day, a, b) for a, b in parts if b > a)
