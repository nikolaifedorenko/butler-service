"""Помощники Графика (вне расчётного ядра): окно смены, смена ячейки, согласованное отсутствие.

Раньше жили в app/timesheet.py вместе со старым движком. Движок удалён (спецификация v4,
раздел 17); здесь осталось только то, что нужно Графику, документам и экранам отметок.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Setting, ShiftType

# прочие правила объекта, не относящиеся к расчёту часов
DEFAULT_RULES = {
    "timeoff_default_hours": "8",
    "photo_retention_days": "180",
    "photo_max_mb": "12",
    "video_max_mb": "50",
    "video_retention_days": "180",
}
RULE_DESCRIPTIONS = {
    "timeoff_default_hours": "Часы «выходного за часы», если стандартное окно смен сотрудника не определилось "
                             "(обычно берётся окно его смены из Табеля)",
    "photo_retention_days": "Хранение фото ночных отчётов и электрокаров в днях (0 — хранить всегда)",
    "photo_max_mb": "Наибольший размер загружаемого фото, МБ (оригиналы не сжимаются)",
    "video_max_mb": "Наибольший размер загружаемого видео, МБ (50 — предел отправки в Telegram)",
    "video_retention_days": "Хранение видео в днях (0 — хранить всегда)",
}
INT_RULES = {"timeoff_default_hours", "photo_retention_days", "photo_max_mb",
             "video_max_mb", "video_retention_days"}


def coerce_rules(raw: dict) -> dict:
    out: dict = {}
    for key, default in DEFAULT_RULES.items():
        val = raw.get(key, default)
        try:
            out[key] = int(float(val)) if key in INT_RULES else str(val)
        except (TypeError, ValueError):
            out[key] = int(default)
    return out


def load_rules(db: Session) -> dict:
    return coerce_rules({s.key: s.value for s in db.scalars(select(Setting))})


def rule_options() -> list[dict]:
    return [{"key": k, "value": DEFAULT_RULES[k], "description": RULE_DESCRIPTIONS.get(k, ""),
             "type": "int" if k in INT_RULES else "str"} for k in DEFAULT_RULES]


def parse_hhmm(value: str) -> tuple[int, int]:
    try:
        h, m = value.split(":")
        return int(h), int(m)
    except Exception:
        return 0, 0


def at(day: dt.date, hhmm: str, plus_days: int = 0) -> dt.datetime:
    h, m = parse_hhmm(hhmm)
    return dt.datetime(day.year, day.month, day.day, h, m) + dt.timedelta(days=plus_days)


def shift_window(shift: Optional[ShiftType], date: dt.date, rules: Optional[dict] = None):
    """Плановое окно смены Графика (локальное naive): (начало, конец); для отсутствий — (None, None)."""
    if not shift or shift.kind != "work" or not shift.start_time or not shift.end_time:
        return None, None
    start = at(date, shift.start_time)
    s_min = parse_hhmm(shift.start_time)[0] * 60 + parse_hhmm(shift.start_time)[1]
    e_min = parse_hhmm(shift.end_time)[0] * 60 + parse_hhmm(shift.end_time)[1]
    plus = 1 if (shift.overnight or e_min <= s_min) else 0
    return start, at(date, shift.end_time, plus)





def month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    first = dt.date(year, month, 1)
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    return first, nxt - dt.timedelta(days=1)
