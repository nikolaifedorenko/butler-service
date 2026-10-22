"""Разбор произвольного цикла графика: «РРВВВВРР», «11000011», «Р Р В В» (Р/В, 1/0, W/O).

Им пользуется базовый цикл сотрудника (base_schedule). Генераторы «N/M» и пресеты жили здесь
для массового заполнения Графика (POST /api/schedule/fill-pattern) — операция удалена по
решению владельца В-7 (аудит 22.10.2026).
"""
from __future__ import annotations

import re

WORK_CHARS = {"р", "r", "w", "1", "я", "+", "work"}
OFF_CHARS = {"в", "v", "o", "0", "вых", "-", "off"}


def parse_custom_cycle(cycle: str) -> list[bool]:
    """«РРВВВВРР» / «11000011» / «Р Р В В» → список [рабочий?]."""
    raw = (cycle or "").strip().lower()
    if not raw:
        raise ValueError("Пустой цикл: задайте последовательность вроде «РРВВВВРР»")
    tokens = [t for t in re.split(r"[\s,;]+", raw) if t]
    out: list[bool] = []
    if all(len(t) == 1 for t in tokens):
        for tok in tokens:
            if tok in WORK_CHARS:
                out.append(True)
            elif tok in OFF_CHARS:
                out.append(False)
            else:
                raise ValueError(f"Непонятный символ цикла: «{tok}» (ожидается Р или В)")
    else:
        # строка слитно: разбираем посимвольно
        for ch in raw.replace(" ", ""):
            if ch in WORK_CHARS:
                out.append(True)
            elif ch in OFF_CHARS:
                out.append(False)
            else:
                raise ValueError(f"Непонятный символ цикла: «{ch}» (ожидается Р или В)")
    if not out:
        raise ValueError("Пустой цикл")
    if not any(out):
        raise ValueError("В цикле нет рабочих дней")
    return out

