"""Общие преобразования адаптеров: локальное naive-время прототипа ↔ UTC-aware,
naive-UTC хранение Графика ↔ UTC-aware."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from app.core.config import settings as app_settings

TZ_NAME = app_settings.app_tz
TZ = ZoneInfo(TZ_NAME)


def local_naive_to_utc(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=TZ).astimezone(dt.timezone.utc)


def utc_to_local_naive(value: dt.datetime) -> dt.datetime:
    return value.astimezone(TZ).replace(tzinfo=None)


def utc_naive_to_aware(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=dt.timezone.utc)


def local_midnight_utc(day: dt.date, tz=None) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(0), tz or TZ).astimezone(dt.timezone.utc)


def eid(value: int | str) -> str:
    return str(value)


def emp_pk(employee_id: str) -> int:
    return int(employee_id)

