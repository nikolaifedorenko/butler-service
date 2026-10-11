"""Округление знакового остатка до ближайшего кратного шагу; ровно половина — вверх по
абсолютной величине (от нуля); знак сохраняется, кроме округления до нуля (4.6)."""
from __future__ import annotations


def round_signed(value: int, step: int) -> int:
    sign = -1 if value < 0 else 1
    whole, rest = divmod(abs(value), step)
    grids = whole + 1 if rest * 2 >= step else whole
    return sign * grids * step
