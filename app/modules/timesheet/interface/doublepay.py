"""API дней двойной оплаты (производственный календарь) и ВИП-периодов сотрудников.

Правила — в ``application/doublepay_edit.py``; роутер разбирает запрос и проверяет право.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..application import doublepay_edit
from ..application.doublepay_edit import DaysIn, VipIn
from .schemas import DoubleCalendarOut, DoubleDayDeletedOut, DoubleDaysAddedOut, VipAddedOut, VipDeletedOut

router = APIRouter(prefix="/api/doublepay", tags=["doublepay"])


@router.get("", response_model=DoubleCalendarOut)
def get_doublepay(year: Optional[int] = None, principal: Principal = Depends(require_perm("settings.view")),
                  db: Session = Depends(get_db)):
    """Календарь двойных дней (за год или весь) и ВИП-периоды."""
    return doublepay_edit.calendar(db, year)


@router.post("/days", response_model=DoubleDaysAddedOut)
def add_days(payload: DaysIn, principal: Principal = Depends(require_perm("settings.doublepay")),
             db: Session = Depends(get_db)):
    """Добавить дни двойной оплаты: списком дат или периодом с фильтром по дням недели."""
    return doublepay_edit.add_days(db, principal, payload)


@router.delete("/days/{day_id}", response_model=DoubleDayDeletedOut)
def delete_day(day_id: int, principal: Principal = Depends(require_perm("settings.doublepay")),
               db: Session = Depends(get_db)):
    return {"ok": True, "deleted": doublepay_edit.delete_day(db, principal, day_id)}


@router.post("/vip", response_model=VipAddedOut)
def add_vip(payload: VipIn, principal: Principal = Depends(require_perm("settings.doublepay")),
            db: Session = Depends(get_db)):
    """Назначить сотруднику период двойных переработок (работа с ВИП-гостем)."""
    return {"ok": True, "item": doublepay_edit.add_vip(db, principal, payload)}


@router.delete("/vip/{vip_id}", response_model=VipDeletedOut)
def delete_vip(vip_id: int, principal: Principal = Depends(require_perm("settings.doublepay")),
               db: Session = Depends(get_db)):
    return {"ok": True, "deleted": doublepay_edit.delete_vip(db, principal, vip_id)}
