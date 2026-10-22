"""Периоды и цепочка «предыдущий/следующий» (16.1 п.7, v7.1/R36): месяц либо половина
месяца по настройке Settings.period_granularity; ядро работает с произвольным Period."""
from __future__ import annotations

import calendar
import datetime as dt

from ..domain.settings.types import GRANULARITY_HALF_MONTH
from ..domain.types.entities import Employment, Period


def month_period(year: int, month: int) -> Period:
    last = calendar.monthrange(year, month)[1]
    return Period(dt.date(year, month, 1), dt.date(year, month, last))


def half_month_period(year: int, month: int, half: int) -> Period:
    last = calendar.monthrange(year, month)[1]
    if half == 1:
        return Period(dt.date(year, month, 1), dt.date(year, month, 15))
    return Period(dt.date(year, month, 16), dt.date(year, month, last))


def period_containing(day: dt.date, granularity: str, half: int | None = None) -> Period:
    if granularity != GRANULARITY_HALF_MONTH:
        return month_period(day.year, day.month)
    return half_month_period(day.year, day.month, 1 if day.day <= 15 else 2)


def settings_for_now(now: dt.datetime, ports):
    """Settings месяца, содержащего ЛОКАЛЬНОЕ «сегодня», и это «сегодня» (16.2,
    16.1 п.7).

    «Сегодня» — по tz объекта (§4.4), а tz сам живёт в Settings: двухшаговое
    уточнение — месяц по UTC-дню даёт tz, по нему считается локальный день,
    итоговая версия справочников грузится для месяца локального дня. В обычном
    случае (месяцы совпали) второго load нет вовсе; на границе месяцев
    доска/вкладка берёт версию нового месяца, а не прошлого (ревью 20.10.2026,
    P1-ts-4: раньше Settings грузились по UTC-дню). Уточнение однократное
    (без цикла до неподвижной точки): смена tz между версиями на самой границе —
    крайний случай, достаточный по прецеденту /periods. Возврат: (settings, today).
    """
    from ..domain.time.today_of import today_of

    utc_day = now.astimezone(dt.timezone.utc).date()
    utc_period = month_period(utc_day.year, utc_day.month)
    st = ports.settings.load(utc_period)
    today = today_of(now, st)
    local_period = month_period(today.year, today.month)
    if local_period != utc_period:
        # обычный случай — тот же месяц: второй load не выполняем вовсе (бюджет
        # «≤ 5 батч-запросов», 16.1 п.5, не растёт даже у порта без кэша)
        st = ports.settings.load(local_period)
    return st, today


def next_period(period: Period, granularity: str) -> Period:
    if granularity != GRANULARITY_HALF_MONTH:
        nxt = period.end + dt.timedelta(days=1)
        return month_period(nxt.year, nxt.month)
    if period.start.day == 1:
        return half_month_period(period.start.year, period.start.month, 2)
    nxt = period.end + dt.timedelta(days=1)
    return half_month_period(nxt.year, nxt.month, 1)


def previous_period(period: Period, granularity: str) -> Period:
    if granularity != GRANULARITY_HALF_MONTH:
        prv = period.start - dt.timedelta(days=1)
        return month_period(prv.year, prv.month)
    if period.start.day == 1:
        prv = period.start - dt.timedelta(days=1)
        return half_month_period(prv.year, prv.month, 2)
    return half_month_period(period.start.year, period.start.month, 1)


def is_first_period(period: Period, employment: Employment, granularity: str) -> bool:
    """Первый период цепочки сотрудника — содержащий Employment.start (16.1 п.7, R35/R37)."""
    return previous_period(period, granularity).end < employment.start


def close_month(employee_id: str, year: int, month: int, now, ports):
    """Обёртка «Закрыть месяц» (16.6): пробрасывает now (v7/R10)."""
    from .close_period import close_period
    return close_period(employee_id, month_period(year, month), now, ports)


def recalculate_month(employee_id: str, year: int, month: int, now, ports):
    """Обёртка «Пересчитать» (16.6): пробрасывает now."""
    from .recalculate import recalculate
    return recalculate(employee_id, month_period(year, month), now, ports)
