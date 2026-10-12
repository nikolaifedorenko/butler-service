"""Вкладка «Отметки» — доска «прямо сейчас» (16.2): (a) сколько на работе, (b) сколько
ожидается по Графику, (c) карточки открытых сессий («на работе с …», «забытый уход»
виден как есть), (d) кто ещё должен прийти — ближайший незавершённый ожидаемый
подинтервал (v7.1/R40). Популяция — трудоустроенные на «сегодня» (v7.1/R38).
Тяжёлый конвейер не вызывается; ≤ 5 батч-запросов (16.1 п.4–5)."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal
from ..db import get_db
from ..deps import utc_to_local
from ..engine.application.months import month_period
from ..engine.application.presence_board import presence_board
from ..engine.domain.types.errors import DomainError
from ..engine.interface.views import board_dict
from ..models import Employee
from ..permissions import require_perm
from .engine_common import domain_error_text, emp_brief, engine_ports, now_utc

router = APIRouter(prefix="/api/presence", tags=["presence"])


@router.get("/board")
def board(principal: Principal = Depends(require_perm("presence.view")),
          db: Session = Depends(get_db)):
    now = now_utc()
    ports = engine_ports(db, principal, now)
    utc_today = now.astimezone(dt.timezone.utc).date()
    try:
        st = ports.settings.load(month_period(utc_today.year, utc_today.month))
    except (DomainError, ValueError) as exc:
        raise HTTPException(status_code=409,
                            detail=f"{domain_error_text(exc)}. Доска не соберётся, пока "
                                   "конфигурация не исправлена в разделе «Настройки»") from exc
    result = presence_board(now, ports)
    payload = board_dict(result, str(st.tz))
    ids = [int(i) for i in ({c["employee_id"] for c in payload["open_session_cards"]}
                            | {a["employee_id"] for a in payload["yet_to_come"]})]
    emps = {str(e.id): {**emp_brief(e), "phone": e.phone or "", "telegram": e.telegram or ""}
            for e in db.scalars(select(Employee).where(Employee.id.in_(ids)))} if ids else {}
    for card in payload["open_session_cards"]:
        card["employee"] = emps.get(card["employee_id"], {})
    for item in payload["yet_to_come"]:
        item["employee"] = emps.get(item["employee_id"], {})
    return {"now": utc_to_local(now).isoformat(timespec="minutes"),
            "today": now.astimezone(st.tz).date().isoformat(), **payload}
