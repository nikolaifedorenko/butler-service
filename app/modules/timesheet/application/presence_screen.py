"""Вкладка «Отметки» — доска «прямо сейчас» (16.2): ответ экрана.

(a) сколько на работе, (b) сколько ожидается по Графику, (c) карточки открытых сессий
(«на работе с …», «забытый уход» виден как есть), (d) кто ещё должен прийти — ближайший
незавершённый ожидаемый подинтервал (v7.1/R40). Популяция — трудоустроенные на «сегодня»
(v7.1/R38). Тяжёлый конвейер не вызывается; ≤ 5 батч-запросов (16.1 п.4–5)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.errors import Conflict
from app.core.time import local_iso
from app.modules.people.application import Employee

from .engine_common import emp_brief, engine_ports, no_employee, now_utc
from .months import settings_for_now
from .presence_board import presence_board
from .views import board_dict


def board(db: Session, principal: Principal) -> dict:
    now = now_utc()
    ports = engine_ports(db, principal, now)
    try:
        # Settings месяца ЛОКАЛЬНОГО «сегодня» (16.2) — то же двухшаговое уточнение, что
        # внутри presence_board (общий помощник settings_for_now)
        st, today = settings_for_now(now, ports)
    except ValueError as exc:
        raise Conflict(str(exc)) from exc
    result = presence_board(now, ports)
    payload = board_dict(result, str(st.tz))
    ids = [int(i) for i in ({c["employee_id"] for c in payload["open_session_cards"]}
                            | {a["employee_id"] for a in payload["yet_to_come"]})]
    emps = {str(e.id): {**emp_brief(e), "phone": e.phone or "", "telegram": e.telegram or ""}
            for e in db.scalars(select(Employee).where(Employee.id.in_(ids)))} if ids else {}
    missing = no_employee(phone=None, telegram=None)
    for card in payload["open_session_cards"]:
        card["employee"] = emps.get(card["employee_id"], missing)
    for item in payload["yet_to_come"]:
        item["employee"] = emps.get(item["employee_id"], missing)
    return {"now": local_iso(now, "minutes"),
            "today": today.isoformat(), **payload}
