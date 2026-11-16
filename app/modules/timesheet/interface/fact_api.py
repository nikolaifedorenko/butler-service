"""API вкладки «Факт» — слой 2 модели «График = 4 слоя» (16.4).

Три представления одних и тех же отметок: история сессий, гант «Месяц» и сетка «День».
Правила — в ``application/fact_screen.py``; роутер разбирает запрос и проверяет право.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..application import fact_screen
from .schemas import FactDayOut, FactMonthOut, FactSessionsOut

router = APIRouter(prefix="/api/fact", tags=["fact"])


@router.get("/sessions", response_model=FactSessionsOut)
def sessions(employee_id: int, first: dt.date, last: dt.date,
             principal: Principal = Depends(require_perm("presence.view")),
             db: Session = Depends(get_db)):
    """История сессий «пришёл — ушёл» сотрудника за диапазон (не более 92 дней)."""
    return fact_screen.sessions(db, principal, employee_id, first, last)


@router.get("/month", response_model=FactMonthOut)
def fact_month(year: int, month: int, principal: Principal = Depends(require_perm("presence.view")),
               db: Session = Depends(get_db)):
    """Гант фактических присутствий за месяц."""
    return fact_screen.month(db, principal, year, month)


@router.get("/day", response_model=FactDayOut)
def day_grid(date: dt.date,
             principal: Principal = Depends(require_perm("presence.view")),
             db: Session = Depends(get_db)):
    """Один день глазами движка: отметки, сессии, план и итог по каждому сотруднику."""
    return fact_screen.day(db, principal, date)
