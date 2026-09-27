"""«Факт» для сетки графика: кто реально был на работе в прошлые дни и сегодня.

Берём рассчитанный табель (detail_json — сессии с точным временем) и раскладываем
интервалы работы по календарным дням, чтобы в ячейке графика было видно:
  * интервалы («08–12», «15–24») — включая хвост вчерашней ночной смены и переход в завтра;
  * отклонения: опоздание, ранний уход, несогласованный перерыв, неявка, смена не закрыта;
  * отсутствия (отпуск, больничный, выходной за часы) и согласованное «отпросился с … до …»;
  * работу в выходной (пришёл, хотя по графику отдыхал).
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .deps import local_date
from .models import Punch, TimesheetRow

ATTENTION_STATUSES = {"late", "early", "late_early", "gap", "no_punch", "unclosed", "work_no_plan"}


def _parse_iso(value: str) -> Optional[dt.datetime]:
    try:
        return dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _merge(intervals: list[tuple[dt.datetime, dt.datetime]]):
    out: list[list[dt.datetime]] = []
    for a, b in sorted(intervals, key=lambda x: x[0]):
        if out and a <= out[-1][1]:
            if b > out[-1][1]:
                out[-1][1] = b
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def _fmt(day: dt.date, moment: dt.datetime, end_of_day: bool = False) -> str:
    """Время в пределах суток; конец дня показываем как 24:00."""
    next_midnight = dt.datetime(day.year, day.month, day.day) + dt.timedelta(days=1)
    if end_of_day and moment >= next_midnight:
        return "24:00"
    return f"{moment.hour:02d}:{moment.minute:02d}"


def build_fact_map(db: Session, emp_ids: list[int], first: dt.date, last: dt.date) -> dict:
    """{(employee_id, 'YYYY-MM-DD'): факт дня} для всех дней месяца."""
    if not emp_ids:
        return {}
    lo = first - dt.timedelta(days=1)
    hi = last + dt.timedelta(days=1)
    rows = db.scalars(select(TimesheetRow).where(
        TimesheetRow.employee_id.in_(emp_ids), TimesheetRow.date >= lo, TimesheetRow.date <= hi)).all()

    raw: dict[tuple[int, str], dict] = {}
    for row in rows:
        try:
            detail = json.loads(row.detail_json or "{}")
        except json.JSONDecodeError:
            detail = {}
        key = (row.employee_id, row.date.isoformat())
        raw[key] = {
            "row": row, "detail": detail,
            "sessions": detail.get("sessions", []),
            "warnings": detail.get("warnings", []),
            "gaps": detail.get("gaps", []),
            "partial": detail.get("partial"),
            "plan_segments": detail.get("plan_segments", []),
        }

    # открытые сессии (сотрудник ещё на работе) — только для сегодняшнего дня
    today = local_date()
    open_sessions: dict[int, dt.datetime] = {}
    if first <= today <= last:
        day_start = dt.datetime(today.year, today.month, today.day) - dt.timedelta(days=1)
        punches = db.scalars(select(Punch).where(
            Punch.employee_id.in_(emp_ids), Punch.ts >= day_start).order_by(Punch.ts)).all()
        last_in: dict[int, Optional[Punch]] = {}
        for p in punches:
            if p.kind == "IN":
                last_in[p.employee_id] = p
            else:
                last_in[p.employee_id] = None
        for emp_id, p in last_in.items():
            if p is not None:
                open_sessions[emp_id] = p.ts

    out: dict[tuple[int, str], dict] = {}
    day = first
    while day <= last:
        day_start = dt.datetime(day.year, day.month, day.day)
        day_end = day_start + dt.timedelta(days=1)
        for emp_id in emp_ids:
            collected: list[tuple[dt.datetime, dt.datetime]] = []
            from_prev = to_next = False
            auto_closed = False
            open_now = False
            info = raw.get((emp_id, day.isoformat()))
            for offset in (-1, 0, 1):
                d = day + dt.timedelta(days=offset)
                item = raw.get((emp_id, d.isoformat()))
                if not item:
                    continue
                for sess in item["sessions"]:
                    a = _parse_iso(sess.get("in_raw")) or _parse_iso(sess.get("in_rounded"))
                    b = _parse_iso(sess.get("out_raw")) or _parse_iso(sess.get("out_rounded"))
                    if not a or not b:
                        continue
                    if sess.get("auto_closed"):
                        auto_closed = True
                    cut_a, cut_b = max(a, day_start), min(b, day_end)
                    if cut_b <= cut_a:
                        continue
                    if cut_a == day_start and a < day_start:
                        from_prev = True
                    if cut_b == day_end and b > day_end:
                        to_next = True
                    collected.append((cut_a, cut_b))
            if emp_id in open_sessions and open_sessions[emp_id] < day_end:
                open_now = True
                collected.append((max(open_sessions[emp_id], day_start), day_end))

            intervals = _merge(collected)
            status = info["row"].status if info else ""
            absence_code = info["row"].code if info and not intervals else ""
            fact = {
                "intervals": [[_fmt(day, a), _fmt(day, b, b >= day_end)] for a, b in intervals],
                "raw": [[a.isoformat(timespec="minutes"), b.isoformat(timespec="minutes")]
                        for a, b in intervals],
                "hours": round(sum((b - a).total_seconds() / 3600.0 for a, b in intervals), 2),
                "counted_hours": info["row"].fact_hours if info else 0.0,
                "status": status,
                "attention": status in ATTENTION_STATUSES,
                "late_hours": info["row"].late_hours if info else 0.0,
                "early_hours": info["row"].early_hours if info else 0.0,
                "gap_hours": info["row"].gap_hours if info else 0.0,
                "ot_hours": info["row"].ot_hours if info else 0.0,
                "deficit_hours": info["row"].deficit_hours if info else 0.0,
                "from_prev": from_prev, "to_next": to_next,
                "auto_closed": auto_closed, "open_now": open_now,
                "absence_code": absence_code or "",
                "plan_segments": info["plan_segments"] if info else [],
                "partial": info["partial"] if info else None,
                "warnings": info["warnings"] if info else [],
                "has_row": info is not None,
            }
            out[(emp_id, day.isoformat())] = fact
        day += dt.timedelta(days=1)
    return out
