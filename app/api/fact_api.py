"""Вкладка «Факт» — история сессий (16.4): сырые сессии (начало, конец либо открыта)
за произвольный диапазон на общем ядре pair_marks; три индексных запроса; моменты
исходные, без округления и нарезки — визуализация (шкала, группировка по дням,
подсветка ночных часов) строится фронтендом. Вкладка не зависит ни от чего, кроме
отметок (ни Табеля, ни Графика, ни settle())."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import Principal
from ..db import get_db
from ..deps import TZ
from ..engine.application.view_sessions import view_sessions
from ..engine.domain.types.errors import DomainError
from ..engine.interface.views import session_view_dict
from ..models import Employee
from ..permissions import require_perm
from .engine_common import domain_error_text, emp_brief, engine_ports, now_utc

router = APIRouter(prefix="/api/fact", tags=["fact"])


@router.get("/sessions")
def sessions(employee_id: int, first: dt.date, last: dt.date,
             principal: Principal = Depends(require_perm("presence.view")),
             db: Session = Depends(get_db)):
    if last < first or (last - first).days > 92:
        raise HTTPException(status_code=422, detail="Диапазон: не более 92 дней")
    if not principal.is_manager:
        own = principal.employee.id if principal.employee else None
        if own is None or own != employee_id:
            raise HTTPException(status_code=403,
                                detail="Доступна только своя история сессий")
    from_utc = dt.datetime.combine(first, dt.time(0), TZ).astimezone(dt.timezone.utc)
    to_utc = dt.datetime.combine(last + dt.timedelta(days=1), dt.time(0),
                                 TZ).astimezone(dt.timezone.utc)
    ports = engine_ports(db, principal, now_utc())
    try:
        views = view_sessions(str(employee_id), from_utc, to_utc, ports)
    except DomainError as exc:
        raise HTTPException(status_code=409, detail=domain_error_text(exc))
    emp = db.get(Employee, employee_id)
    return {"employee": emp_brief(emp) if emp else {"id": employee_id},
            "range": {"from": from_utc.isoformat(), "to": to_utc.isoformat(),
                      "first": first.isoformat(), "last": last.isoformat()},
            "sessions": [session_view_dict(v, TZ) for v in views]}
