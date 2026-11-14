"""Общие преобразования адаптеров: границы суток объекта и идентификаторы."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from app.core.config import settings as app_settings

TZ_NAME = app_settings.app_tz
TZ = ZoneInfo(TZ_NAME)


def local_midnight_utc(day: dt.date, tz=None) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(0), tz or TZ).astimezone(dt.UTC)


def eid(value: int | str) -> str:
    return str(value)


def emp_pk(employee_id: str) -> int:
    return int(employee_id)

