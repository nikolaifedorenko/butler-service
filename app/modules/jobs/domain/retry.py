"""Пауза перед повтором упавшей задачи: растёт вдвое с каждой попыткой и ограничена потолком."""
from __future__ import annotations


def retry_delay(attempt: int, base: int = 30, cap: int = 3600) -> int:
    """Секунды до следующей попытки после ``attempt``-й неудачной (1, 2, 3…): base, 2·base, 4·base… не больше cap."""
    if attempt < 1:
        raise ValueError("номер попытки начинается с 1")
    return min(cap, base * 2 ** min(attempt - 1, 30))
