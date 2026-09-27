"""
Генераторы графиков.

Поддерживаются:
  * числовые циклы «N/M» с любыми числами: 2/2, 3/3, 4/3, 4/2, 1/3 …;
  * привязка к дням недели: 5/2, 6/1 — с выбором, какие именно дни выходные;
  * произвольный цикл строкой: «РРВВВВРР», «ВВРРРРВВ» … (Р/В, 1/0, W/O) —
    любые переходы «смена-смена», включая несимметричные недели;
  * сдвиг фазы (offset), чтобы бригады не совпадали.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Iterable

PRESETS: dict[str, dict] = {
    "2/2": {"title": "2/2 — два рабочих, два выходных"},
    "3/3": {"title": "3/3 — три рабочих, три выходных"},
    "4/2": {"title": "4/2 — четыре рабочих, два выходных"},
    "4/3": {"title": "4/3 — четыре рабочих, три выходных"},
    "5/2": {"title": "5/2 — пятидневка (выходные выбираются)"},
    "6/1": {"title": "6/1 — шестидневка (выходной выбирается)"},
    "1/1": {"title": "1/1 — сутки через сутки"},
    "1/2": {"title": "1/2 — сутки через двое"},
    "1/3": {"title": "1/3 — сутки через трое"},
}

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


def pattern_days(pattern: str, start: dt.date, days: int, offset: int = 0,
                 off_weekdays: Iterable[int] = (5, 6), cycle: str = "") -> list[bool]:
    """
    Список из `days` значений: True — рабочий, False — выходной.
    off_weekdays — номера дней недели для выходных (0=пн … 6=вс) для режимов 5/2 и 6/1.
    cycle — произвольная строка цикла для pattern="custom".
    """
    pattern = (pattern or "").strip()
    result: list[bool] = []

    if pattern.lower() in ("custom", "произвольный", ""):
        seq = parse_custom_cycle(cycle)
        for i in range(days):
            result.append(seq[(i + offset) % len(seq)])
        return result

    m = re.fullmatch(r"(\d+)\s*/\s*(\d+)", pattern)
    if not m:
        raise ValueError(f"Неизвестный график: {pattern} (примеры: 2/2, 4/3, 5/2 или custom + цикл «РРВВ»)")
    work_n, off_n = int(m.group(1)), int(m.group(2))
    if work_n <= 0 or off_n < 0 or work_n + off_n <= 0:
        raise ValueError("Некорректные числа графика")

    off_set = set(off_weekdays)
    for i in range(days):
        day = start + dt.timedelta(days=i)
        if pattern in ("5/2", "6/1"):
            result.append(day.weekday() not in off_set)
        else:
            cycle_len = work_n + off_n
            result.append(((i + offset) % cycle_len) < work_n)
    return result


def pattern_list() -> list[dict]:
    return [{"id": k, "title": v["title"]} for k, v in PRESETS.items()] + [
        {"id": "custom", "title": "Произвольный цикл (РРВВВВРР…) — любые переходы смена/выходной"}]


def validate_pattern(pattern: str, cycle: str = "") -> None:
    """Бросает ValueError с человекочитаемым текстом, если график задан неверно."""
    if pattern.lower() in ("custom", "произвольный", ""):
        parse_custom_cycle(cycle)
    else:
        pattern_days(pattern, dt.date(2026, 1, 1), 1)


def daterange(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    day = start
    while day <= end:
        yield day
        day += dt.timedelta(days=1)
