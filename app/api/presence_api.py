"""«Кто на работе» / «Посещения»: сейчас на работе, по графику сегодня, отлучились, ожидаются."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import Principal
from ..db import get_db
from ..deps import utc_to_local
from ..engine.adapters.bulk import build_bulk_ports
from ..engine.adapters.clock import SystemClock
from ..engine.application.presence_board import EXPECTED, PRESENT, STEPPED_OUT, presence_board
from ..models import Employee
from ..permissions import require_perm
from .engine_common import emp_brief, period_employees

router = APIRouter(prefix="/api/presence", tags=["presence"])


def _hm(value) -> str | None:
    return utc_to_local(value).strftime("%H:%M") if value else None


def _item(emp: Employee, r, now) -> dict:
    brief = emp_brief(emp)
    since_h = round((now - r.since).total_seconds() / 3600, 1) if r.since else None
    return {"employee": {**brief, "phone": emp.phone or "", "telegram": emp.telegram or ""},
            "since": _hm(r.since), "elapsed_hours": since_h, "expected_at": _hm(r.expected_at),
            "expected_until": _hm(r.expected_until), "left_at": _hm(r.left_at), "overdue": r.overdue,
            "planned_today": r.planned_today,
            "plan": [f"{a // 60:02d}:{a % 60:02d}–{b // 60:02d}:{b % 60:02d}" if b < 1440 else
                     f"{a // 60:02d}:{a % 60:02d}–24:00" for a, b in r.subintervals]}


@router.get("/board")
def board(principal: Principal = Depends(require_perm("presence.view")), db: Session = Depends(get_db)):
    clock = SystemClock()
    now = clock.now()
    today = utc_to_local(now).date()
    emps = [e for e in period_employees(db, today, today) if e.active]
    ports = build_bulk_ports(db, [e.id for e in emps], today - dt.timedelta(days=1), today, clock=clock)
    rows = presence_board([str(e.id) for e in emps], ports)
    by_id = {str(e.id): e for e in emps}
    groups = {PRESENT: [], STEPPED_OUT: [], EXPECTED: []}
    for r in rows:
        if r.status in groups:
            groups[r.status].append(_item(by_id[r.employee_id], r, now))
    groups[PRESENT].sort(key=lambda x: x["since"] or "")
    groups[STEPPED_OUT].sort(key=lambda x: x["expected_at"] or "")
    groups[EXPECTED].sort(key=lambda x: x["expected_at"] or "")
    return {"now": utc_to_local(now).isoformat(timespec="minutes"), "today": today.isoformat(),
            "counts": {"present": len(groups[PRESENT]), "planned_today": sum(1 for r in rows if r.planned_today)},
            "present": groups[PRESENT], "stepped_out": groups[STEPPED_OUT], "expected": groups[EXPECTED]}
