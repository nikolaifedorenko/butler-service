"""Время (ядро, R5): единственный источник «сейчас», часового пояса объекта и типа колонки.

Три вида времени (ADR-0013, раздел 2):

* момент — дата и время с поясом; в базе всегда UTC (тип колонки ``Moment``), в коде —
  ``now()`` и значения из базы. Момент без пояса — ошибка, а не «наверное, UTC»;
* местное время объекта — тот же момент в поясе ``TZ``: ``to_local()``, ``local_now()``,
  ``from_local()``; строка для API — ``local_iso()``;
* гостиничная и табельная дата — ``date``: ``local_date()``.

Пояс объекта читается только здесь: при втором отеле функции получат параметр «отель».
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator

from .config import settings

TZ = ZoneInfo(settings.app_tz)


def now() -> dt.datetime:
    """Текущий момент (UTC, с поясом)."""
    return dt.datetime.now(dt.UTC)


def to_local(moment: dt.datetime | None) -> dt.datetime | None:
    """Момент в поясе объекта (с поясом)."""
    return None if moment is None else moment.astimezone(TZ)


def local_now() -> dt.datetime:
    """Текущий момент в поясе объекта (с поясом)."""
    return dt.datetime.now(TZ)


def local_date() -> dt.date:
    """Сегодняшняя дата объекта."""
    return local_now().date()


def from_local(value: dt.datetime) -> dt.datetime:
    """Местное время объекта без пояса (ввод пользователя, «08:00 такого-то дня») → момент."""
    if value.tzinfo is not None:
        raise ValueError("from_local ждёт время без пояса")
    return value.replace(tzinfo=TZ)


def local_midnight(day: dt.date) -> dt.datetime:
    """Начало суток объекта как момент."""
    return dt.datetime.combine(day, dt.time(0), TZ)


def local_iso(moment: dt.datetime | None, timespec: str = "seconds") -> str | None:
    """Строка времени для API: местное время объекта без смещения («2026-11-12T10:30:00»)."""
    return None if moment is None else moment.astimezone(TZ).replace(tzinfo=None).isoformat(timespec=timespec)


def utc_iso(moment: dt.datetime | None, timespec: str = "auto") -> str | None:
    """Строка времени для API в UTC без смещения — формат служебных меток (создано, закрыто)."""
    return None if moment is None else moment.astimezone(dt.UTC).replace(tzinfo=None).isoformat(timespec=timespec)


class Moment(TypeDecorator):
    """Колонка-момент: ``timestamptz``. Принимает только время с поясом, отдаёт UTC с поясом."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            raise ValueError(f"момент без часового пояса: {value!r} — используйте core.time.now() или from_local()")
        return value

    def process_result_value(self, value, dialect):
        return None if value is None else value.astimezone(dt.UTC)


# ── прежние функции времени без пояса: остаются до перевода ночного отчёта, электрокаров,
#    уведомлений и шахматки (вторая часть шага 3в) ──
def now_local() -> dt.datetime:
    """Текущее время объекта без пояса. Устарело: local_now()."""
    return dt.datetime.now(TZ).replace(tzinfo=None)


def month_name(month: int) -> str:
    names = ["январь", "февраль", "март", "апрель", "май", "июнь",
             "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
    return names[(month - 1) % 12]


WD_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

