"""Помощники приёмочных тестов движка: компактная запись Табеля, отметок и Графика."""
from __future__ import annotations

import datetime as dt
from dataclasses import replace
from zoneinfo import ZoneInfo

from app.engine.domain.flags.evaluate_flags import evaluate_flags
from app.engine.domain.pipeline.settle import settle
from app.engine.domain.settings.defaults import default_settings
from app.engine.domain.settings.types import MOD_COUNTS_IN_UT, MOD_DOUBLE, MOD_PAYS, MOD_PLAN_EQUALS_FACT, Modifier
from app.engine.domain.types.entities import Absence, Adjustment, Day, DeferredBlock, Mark, Period, Shift

TZ = ZoneInfo("Europe/Moscow")
UTC = dt.timezone.utc
EMP = "e1"
Y = 2026
H = 60


def d(day: int, month: int = 10) -> dt.date:
    return dt.date(Y, month, day)


def at(day: int, hh: int, mm: int = 0, month: int = 10) -> dt.datetime:
    return dt.datetime(Y, month, day, hh, mm, tzinfo=TZ).astimezone(UTC) if hh < 24 else \
        dt.datetime(Y, month, day, 0, mm, tzinfo=TZ).astimezone(UTC) + dt.timedelta(days=1)


def day(n: int, value: str, month: int = 10, group: str = "Смена 1") -> Day:
    code, _, hours = value.partition(" ")
    return Day(d(n, month), code, int(float(hours) * H) if hours else 0, EMP, group)


def mk(kind: str, n: int, hh: int, mm: int = 0, month: int = 10) -> Mark:
    return Mark(EMP, at(n, hh, mm, month), kind)


def IN(n, hh, mm=0, month=10):
    return mk("in", n, hh, mm, month)


def OUT(n, hh, mm=0, month=10):
    return mk("out", n, hh, mm, month)


def mod(name, value, n=None, month=10, employee=None, group=None):
    return Modifier(name, value, employee, group, d(n, month) if n else None)


def double(n, month=10):
    return mod(MOD_DOUBLE, True, n, month)


def unpaid(n, month=10):
    return mod(MOD_PAYS, False, n, month)


def not_in_ut(n, month=10):
    return mod(MOD_COUNTS_IN_UT, False, n, month)


def pef(n, value=True, month=10):
    return mod(MOD_PLAN_EQUALS_FACT, value, n, month)


def settings(*mods, **kw):
    st = default_settings()
    return replace(st, modifiers=tuple(mods), employee_groups={EMP: kw.pop("group", "Смена 1")}, **kw)


def period_of(days):
    return Period(min(x.day for x in days), max(x.day for x in days))


def close_now(period: Period) -> dt.datetime:
    e = period.end + dt.timedelta(days=1)
    return dt.datetime(e.year, e.month, e.day, tzinfo=TZ).astimezone(UTC)


def run(days, marks=(), bank=0, mode="close", st=None, now=None, period=None, adjustments=(),
        deferred=(), opening=None, prev_step=None):
    st = st or settings()
    period = period or period_of(days)
    now = now or close_now(period)
    return settle(period, days, list(marks), opening, bank * H, list(adjustments), list(deferred), st, now,
                  mode, prev_step or st.step_minutes)


def shift(n1, h1, n2, h2, month=10):
    return Shift(EMP, at(n1, h1, month=month), at(n2, h2, month=month))


def shifts_from_tabel(days, st):
    """«График построен из Табеля по окнам Т2» (общие условия раздела 11)."""
    from app.engine.domain.day_card.value_of import value_of
    out = []
    for x in days:
        w = st.windows.get(value_of(x, st))
        for a, b in (w.segments if w else ()):
            base = dt.datetime(x.day.year, x.day.month, x.day.day, tzinfo=TZ).astimezone(UTC)
            out.append(Shift(EMP, base + dt.timedelta(minutes=a), base + dt.timedelta(minutes=b)))
    return out


def flags(days, marks=(), result=None, shifts=None, absences=(), st=None, now=None, period=None, opening=None):
    st = st or settings()
    period = period or period_of(days)
    now = now or close_now(period)
    result = result or run(days, marks, st=st, now=now, period=period, opening=opening, mode="view")
    sh = shifts_from_tabel(days, st) if shifts is None else shifts
    fr = evaluate_flags(period, days, result.cards, list(marks), opening, sh, list(absences), st, now)
    return [(f.day, f.code) for f in fr.flags], fr


def absence(n, h1, h2, month=10):
    return Absence(EMP, d(n, month), h1 * H, h2 * H)


def ut(result):
    """УТ в часах без пустых дней: {day: {tariff: hours}}."""
    return {k: {t: m / H for t, m in v.items()} for k, v in result.mgmt_timesheet.items() if v}


def hours(minutes):
    return minutes / H


__all__ = [n for n in dir() if not n.startswith("_")] + ["Adjustment", "DeferredBlock"]
