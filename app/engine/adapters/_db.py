"""Общие преобразования адаптеров: локальное naive-время прототипа ↔ UTC-aware."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from ...config import settings as app_settings

TZ_NAME = app_settings.app_tz
TZ = ZoneInfo(TZ_NAME)


def local_naive_to_utc(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=TZ).astimezone(dt.timezone.utc)


def utc_to_local_naive(value: dt.datetime) -> dt.datetime:
    return value.astimezone(TZ).replace(tzinfo=None)


def eid(value: int | str) -> str:
    return str(value)


def emp_pk(employee_id: str) -> int:
    return int(employee_id)


def days_of(start: dt.date, end: dt.date) -> list[dt.date]:
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
