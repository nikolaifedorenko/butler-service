"""API словаря «Смены и отсутствия» и значений Табеля. Правила — в ``application/shift_dictionary.py``."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal, current_principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..application import shift_dictionary
from ..application.shift_dictionary import ShiftTypeIn
from .schemas import (
    DayCodesOut,
    ShiftArchivedOut,
    ShiftRestoredOut,
    ShiftRevisionsOut,
    ShiftTypeOut,
    TabelValuesOut,
)

router = APIRouter(prefix="/api", tags=["directory"])


@router.get("/tabel-values", response_model=TabelValuesOut)
def tabel_values(principal: Principal = Depends(current_principal),
                 db: Session = Depends(get_db)):
    """Значения рабочего дня для карточки сотрудника и диалогов перевода: код, часы и окно."""
    return {"values": shift_dictionary.tabel_values(db)}


@router.get("/shift-types", response_model=list[ShiftTypeOut])
def list_shift_types(include_archived: bool = False,
                     principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Словарь смен. Архивные скрыты; include_archived=true — показать и их.
    Чтение — любому вошедшему (легенда графика), правки — менеджерам."""
    return shift_dictionary.list_shift_types(db, include_archived)


@router.get("/shift-types/tabel-codes", response_model=DayCodesOut)
def shift_tabel_codes(principal: Principal = Depends(current_principal),
                      db: Session = Depends(get_db)):
    """Коды Табеля для редактора смены: поле «код в табеле» — выбор из существующих кодов."""
    return {"codes": shift_dictionary.tabel_codes(db)}


@router.post("/shift-types", response_model=ShiftTypeOut)
def create_shift_type(payload: ShiftTypeIn, principal: Principal = Depends(require_perm("settings.edit")),
                      db: Session = Depends(get_db)):
    return shift_dictionary.create_shift_type(db, principal, payload)


@router.put("/shift-types/{type_id}", response_model=ShiftTypeOut)
def update_shift_type(type_id: int, payload: ShiftTypeIn,
                      principal: Principal = Depends(require_perm("settings.edit")), db: Session = Depends(get_db)):
    """Правка смены не ломает прошлое: прежние значения остаются ревизией, новые действуют
    с ``effective_from`` (по умолчанию — с сегодняшнего дня)."""
    return shift_dictionary.update_shift_type(db, principal, type_id, payload)


@router.delete("/shift-types/{type_id}", response_model=ShiftArchivedOut)
def delete_shift_type(type_id: int, principal: Principal = Depends(require_perm("settings.edit")),
                      db: Session = Depends(get_db)):
    """«Удаление» смены — архивация: прошлые графики продолжают считаться по ней."""
    return {"ok": True, "archived": True, "shift": shift_dictionary.archive_shift_type(db, principal, type_id)}


@router.post("/shift-types/{type_id}/restore", response_model=ShiftRestoredOut)
def restore_shift_type(type_id: int, principal: Principal = Depends(require_perm("settings.edit")),
                       db: Session = Depends(get_db)):
    """Вернуть смену из архива в словарь."""
    return {"ok": True, "shift": shift_dictionary.restore_shift_type(db, principal, type_id)}


@router.get("/shift-types/{type_id}/revisions", response_model=ShiftRevisionsOut)
def shift_revisions(type_id: int, principal: Principal = Depends(require_perm("settings.view")),
                    db: Session = Depends(get_db)):
    """История значений смены: какие часы действовали в прошлом."""
    return shift_dictionary.revisions(db, type_id)
