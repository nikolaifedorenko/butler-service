"""Пересечение интервала с минутными границами (служебный помощник стадии 5)."""
from __future__ import annotations

from ..types.entities import Interval


def overlap_minutes(iv: Interval, lo: int, hi: int) -> int:
    return max(0, min(iv.end_minute, hi) - max(iv.start_minute, lo))
