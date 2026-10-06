"""«Факт» для сетки Графика: кто реально был на работе (интервалы по отметкам) и флаги дня.

Источник — расчётный движок v4: исходные интервалы присутствия (по реальным отметкам, правило
переноса состояния через полночь, спец. 4.3) и информационные флаги evaluate_flags().
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from .engine.adapters.bulk import build_bulk_ports
from .engine.application.compute import compute
from .engine.application.load_inputs import load_inputs
from .engine.application.periods import month_period
from .engine.domain.presence.presence_intervals import presence_intervals
from .engine.domain.presence.sort_marks import sort_marks
from .engine.domain.time.to_raw_mark import to_raw_mark
from .engine.domain.time.today_of import today_of
from .engine.domain.types.errors import DomainError
from .engine.interface.formatting import FLAG_TITLES

ATTENTION_FLAGS = {"LATE", "EARLY_DEPARTURE", "MISSED_DAY", "OFF_SHIFT_ATTENDANCE", "SESSION_OPEN",
                   "ACTIVITY_REQUIRES_REVIEW"}


def _hm(m: int) -> str:
    return "24:00" if m >= 1440 else f"{m // 60:02d}:{m % 60:02d}"


def _months(first: dt.date, last: dt.date):
    y, m = first.year, first.month
    while (y, m) <= (last.year, last.month):
        yield month_period(y, m)
        y, m = (y + (m == 12), m % 12 + 1)


def _fact_for(view, inp, now) -> dict:
    st = inp.st
    raw = sort_marks([to_raw_mark(m, st) for m in ([inp.opening_mark] if inp.opening_mark else []) + list(inp.marks)])
    days = [c.day for c in view.settle.cards] or [inp.period.start]
    pres = presence_intervals(days, raw, now, today_of(now, st.tz), st.tz)
    out = {}
    for c in view.settle.cards:
        ivs = pres.intervals.get(c.day, ())
        flags = view.flags_of(c.day)
        codes = [f.code for f in flags]
        out[c.day.isoformat()] = {
            "intervals": [[_hm(i.start_minute), _hm(i.end_minute)] for i in ivs],
            "hours": round(sum(i.length for i in ivs) / 60, 2),
            "counted_hours": c.full_fact_minutes / 60, "ot_hours": c.overtime_minutes / 60,
            "deficit_hours": c.debt_minutes / 60, "status": codes[0] if codes else "",
            "flags": [{"code": f, "title": FLAG_TITLES.get(f, f)} for f in codes],
            "attention": any(f in ATTENTION_FLAGS for f in codes),
            "from_prev": pres.open_at_start.get(c.day, False), "to_next": pres.open_at_end.get(c.day, False),
            "open_now": "SESSION_OPEN" in codes, "value": c.timesheet_value, "has_row": True,
            "late_hours": 0.0, "early_hours": 0.0, "gap_hours": 0.0, "auto_closed": False,
            "absence_code": "", "plan_segments": [], "partial": None, "warnings": [],
        }
    return out


def build_fact_map(db: Session, emp_ids: list[int], first: dt.date, last: dt.date) -> dict:
    """{(employee_id, 'YYYY-MM-DD'): факт дня} для дней [first, last]."""
    if not emp_ids:
        return {}
    ports = build_bulk_ports(db, emp_ids, first.replace(day=1), last)
    now = ports.clock.now()
    today = today_of(now, ports.settings.load(month_period(first.year, first.month)).tz)
    out: dict = {}
    for period in _months(first, min(last, today)):
        for emp_id in emp_ids:
            try:
                inp = load_inputs(str(emp_id), period, ports)
                view = compute(inp, now, "view")
            except DomainError:
                continue
            for day, fact in _fact_for(view, inp, now).items():
                if first.isoformat() <= day <= last.isoformat():
                    out[(emp_id, day)] = fact
    return out
