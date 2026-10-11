"""Разбор канонического ключа CFG-WINDOWS (3.3): «<код> <часы>» → (код, минуты) | None.

Канон: ровно один пробел; часы — десятичная дробь через запятую, не более двух знаков,
без хвостовых нулей; минуты = часы × 60 точно.
"""
from __future__ import annotations

import re

_KEY = re.compile(r"^(?P<code>\S+) (?P<hours>\d+(?:,\d{1,2})?)$")


def parse_key(key: str) -> tuple[str, int] | None:
    """None — ключ неканоничен либо часы не дают целое число минут."""
    m = _KEY.match(key)
    if m is None:
        return None
    whole, _, frac = m.group("hours").partition(",")
    if frac and frac.endswith("0"):
        return None                                  # хвостовой ноль: «10,50», «10,0»
    hundredths = int(whole) * 100 + (int(frac.ljust(2, "0")) if frac else 0)
    if hundredths * 3 % 5 != 0:
        return None                                  # часы × 60 не целое число минут
    return m.group("code"), hundredths * 3 // 5
