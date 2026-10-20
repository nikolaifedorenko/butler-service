"""«План на сегодня» из Графика: общий use-case для отметок и личного кабинета.

Вынесен из app/api/punches.py, потому что нужен двум API-модулям (punches и
auth_routes /me), а модули api не должны импортировать друг друга (контракт
import-linter). Лёгкий расчёт: отрезки смен (generated/manual) минус
согласованные отсутствия — доменные функции Графика, БЕЗ тяжёлого конвейера.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import TZ, now_local

from ..adapters.orm import ScheduleAbsence, ScheduleShift


def to_local(value: dt.datetime) -> dt.datetime:
    return value.replace(tzinfo=dt.timezone.utc).astimezone(TZ).replace(tzinfo=None)


def day_bounds_utc(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    lo = dt.datetime.combine(day, dt.time(0), TZ).astimezone(dt.timezone.utc)
    return lo, lo + dt.timedelta(days=1)


def plan_for_date(db: Session, emp_id: int, today: dt.date,
                   at_ts: Optional[dt.datetime] = None):
    """План на «сегодня» из Графика (generated/manual); ранним утром учитывается
    вчерашняя смена через полночь. Возвращает (shift_brief | None, plan_start, plan_end,
    plan_date, subintervals)."""
    yesterday = today - dt.timedelta(days=1)
    lo, _ = day_bounds_utc(yesterday)
    _, hi = day_bounds_utc(today)
    rows = db.scalars(select(ScheduleShift).where(
        ScheduleShift.employee_id == emp_id, ScheduleShift.start_utc < hi,
        ScheduleShift.end_utc > lo).order_by(ScheduleShift.start_utc)).all()
    now = at_ts or now_local()
    today_rows, y_rows = [], []
    for row in rows:
        start, end = to_local(row.start_utc), to_local(row.end_utc)
        item = {"id": row.id, "source": row.source, "start": start, "end": end,
                "start_hm": start.strftime("%H:%M"), "end_hm": end.strftime("%H:%M"),
                "date": row.date.isoformat()}
        (y_rows if row.date == yesterday else today_rows).append(item)
    active_yesterday = [r for r in y_rows if r["end"] >= now]
    if active_yesterday and not today_rows:
        row = active_yesterday[-1]
        return row, row["start"], row["end"], yesterday, subintervals(db, emp_id, yesterday)
    if today_rows:
        row = today_rows[0]
        return row, row["start"], row["end"], today, subintervals(db, emp_id, today)
    if active_yesterday:
        row = active_yesterday[-1]
        return row, row["start"], row["end"], yesterday, subintervals(db, emp_id, yesterday)
    return None, None, None, today, ()


def subintervals(db: Session, emp_id: int, day: dt.date) -> tuple:
    """Ожидаемые подинтервалы дня: отрезки смен минус согласованные отсутствия
    (доменные функции Графика — лёгкий расчёт вкладки, не тяжёлый конвейер)."""
    from ..domain.schedule.expected_subintervals import expected_subintervals
    from ..domain.schedule.merge_absences import merge_absences
    from ..domain.schedule.shift_segments import merge_spans
    lo, hi = day_bounds_utc(day)
    rows = db.scalars(select(ScheduleShift).where(
        ScheduleShift.employee_id == emp_id, ScheduleShift.start_utc < hi,
        ScheduleShift.end_utc > lo)).all()
    spans = [(max(_start(r), lo), min(_end(r), hi)) for r in rows]
    spans = [(a, b) for a, b in spans if a < b]
    absences = db.scalars(select(ScheduleAbsence).where(
        ScheduleAbsence.employee_id == emp_id, ScheduleAbsence.start_utc < hi,
        ScheduleAbsence.end_utc > lo)).all()
    merged_abs = merge_absences([_absence(a) for a in absences])
    return expected_subintervals(merge_spans(spans), merged_abs, day)


def _start(row: ScheduleShift) -> dt.datetime:
    return row.start_utc.replace(tzinfo=dt.timezone.utc)


def _end(row: ScheduleShift) -> dt.datetime:
    return row.end_utc.replace(tzinfo=dt.timezone.utc)


def _absence(row: ScheduleAbsence):
    from ..domain.types.entities import Absence
    return Absence(str(row.employee_id), _start(row), _end(row))
