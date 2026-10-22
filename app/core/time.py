"""Время объекта — единственный источник TZ и «сейчас» (ядро, R5).

Преобразовано из app/deps.py в фазе C1 (20.10.2026, EXECUTION-SPEC-v2 §5.1):
TZ/now_local/local_date/utc_to_local + календарные подписи (месяц, день недели)
и utcnow() (перенесён из app/models/common.py). Форматно-защитные хелперы
(safe_sheet_cell, normalize_hex_color) переехали в core/format.py, транслитерация
логинов (slugify_username) — в app/names.py.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from .config import settings

TZ = ZoneInfo(settings.app_tz)


def now_local() -> dt.datetime:
    """Текущее время объекта (наивный datetime в часовом поясе APP_TZ)."""
    return dt.datetime.now(TZ).replace(tzinfo=None)


def local_date() -> dt.date:
    return now_local().date()


def utc_to_local(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(TZ).replace(tzinfo=None)


def utcnow() -> dt.datetime:
    """Наивный UTC — для меток хранения (ts аудита, created_at и т.п.)."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def month_name(month: int) -> str:
    names = ["январь", "февраль", "март", "апрель", "май", "июнь",
             "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
    return names[(month - 1) % 12]


WD_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

