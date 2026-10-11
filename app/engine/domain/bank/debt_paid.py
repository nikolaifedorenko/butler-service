"""debt_paid_by_cut(minutes, weight) — погашенные минуты долга = физические × вес кода
(4.1: погашение недостачи кодом — по весу)."""
from __future__ import annotations


def debt_paid_by_cut(minutes: int, weight: int) -> int:
    return minutes * weight
