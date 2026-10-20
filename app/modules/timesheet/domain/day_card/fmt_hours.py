"""Формат часов значения Табеля (3.3): минуты → «12», «8,5», «8,25», «10,75».

Десятичная дробь через запятую, не более двух знаков, хвостовые нули не пишутся.
Не человекочитаемое форматирование, а канонический ключ CFG-WINDOWS (RUL-TIMESHEET-VALUE).
"""
from __future__ import annotations


def fmt_hours(minutes: int) -> str:
    if minutes * 5 % 3 != 0:
        raise ValueError(f"minutes not representable with <= 2 decimal digits: {minutes}")
    hundredths = minutes * 5 // 3
    whole, frac = hundredths // 100, hundredths % 100
    if frac == 0:
        return str(whole)
    return f"{whole},{f'{frac:02d}'.rstrip('0')}"
