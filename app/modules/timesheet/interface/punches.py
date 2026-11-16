"""API отметок прихода и ухода: кнопки сотрудника, журнал, статус «я на смене».

Правила — в ``application/punches.py``; роутер разбирает запрос и проверяет право.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal, current_principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..application import punches
from ..application.punches import NoteIn, PunchIn
from .schemas import PunchDeletedOut, PunchDoneOut, PunchNoteOut, PunchRowOut, PunchStatusOut

router = APIRouter(prefix="/api/punches", tags=["punches"])


@router.get("/status", response_model=PunchStatusOut)
def my_status(principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Состояние для личного кабинета: план на сегодня, на смене ли я, сколько отработал."""
    return punches.my_status(db, principal)


@router.post("", response_model=PunchDoneOut)
def punch(payload: PunchIn, principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Кнопки «Пришёл на работу» и «Ушёл с работы».

    Права: отметка за себя — me.punch; чужая отметка или отметка задним числом — punches.manage.
    """
    return punches.punch(db, principal, payload)


@router.get("", response_model=list[PunchRowOut])
def list_punches(date: Optional[dt.date] = None, year: Optional[int] = None, month: Optional[int] = None,
                 employee_id: Optional[int] = None, principal: Principal = Depends(current_principal),
                 db: Session = Depends(get_db)):
    """Журнал отметок. Сотрудник видит только свои, менеджер — всех."""
    return punches.list_punches(db, principal, date, year, month, employee_id)


@router.delete("/{punch_id}", response_model=PunchDeletedOut)
def delete_punch(punch_id: int, principal: Principal = Depends(require_perm("punches.manage")),
                 db: Session = Depends(get_db)):
    """Отменить ошибочную отметку (с записью в аудит)."""
    return {"ok": True, "warning": punches.delete_punch(db, principal, punch_id)}


@router.put("/{punch_id}/note", response_model=PunchNoteOut)
def set_punch_note(punch_id: int, payload: NoteIn,
                   principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Описание переработки: с кем работал и что делал (ставит сотрудник или менеджер)."""
    return {"ok": True, "note": punches.set_punch_note(db, principal, punch_id, payload)}
