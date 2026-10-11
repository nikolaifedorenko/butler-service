"""available_bank(opening, adjustments, credited) — A = нормализованный входящий остаток
+ корректировки + зачисленные неоплаченные (4.8, единственное нормативное место)."""
from __future__ import annotations


def available_bank(opening: int, adjustments: int, credited: int) -> int:
    return opening + adjustments + credited
