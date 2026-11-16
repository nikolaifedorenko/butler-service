"""API вкладки «Табель» (16.5): сетка первичного документа, правка ячеек, заполнение из циклов.

Правила — в ``application/tabel_screen.py``; роутер разбирает запрос и проверяет право.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..application import tabel_screen
from ..application.tabel_screen import BulkIn, CellIn, FillIn, ResetIn
from .schemas import TabelBulkOut, TabelCellSavedOut, TabelFillOut, TabelOut, TabelResetOut

router = APIRouter(prefix="/api/tabel", tags=["tabel"])


@router.get("", response_model=TabelOut)
def get_tabel(year: int, month: int, half: Optional[int] = None,
              principal: Principal = Depends(require_perm("tabel.view")),
              db: Session = Depends(get_db)):
    """Табель периода: месяц либо половина месяца."""
    return tabel_screen.tabel(db, principal, year, month, half)


@router.put("/cell", response_model=TabelCellSavedOut)
def put_cell(payload: CellIn, principal: Principal = Depends(require_perm("tabel.edit")),
             db: Session = Depends(get_db)):
    return {"ok": True, "warning": tabel_screen.put_cell(db, principal, payload)}


@router.post("/bulk", response_model=TabelBulkOut)
def bulk(payload: BulkIn, principal: Principal = Depends(require_perm("tabel.edit")),
         db: Session = Depends(get_db)):
    """Одно значение во много ячеек: записываются все либо ни одной."""
    return tabel_screen.bulk(db, principal, payload)


@router.post("/fill-from-cycles", response_model=TabelFillOut)
def fill(payload: FillIn, principal: Principal = Depends(require_perm("tabel.edit")),
         db: Session = Depends(get_db)):
    """Заполнить Табель из циклов графика; закрытые периоды не трогаются."""
    return tabel_screen.fill(db, principal, payload)


@router.post("/reset", response_model=TabelResetOut)
def reset(payload: ResetIn, principal: Principal = Depends(require_perm("tabel.edit")),
          db: Session = Depends(get_db)):
    """«Сбросить»: убрать ручные коды периода и вернуть автозаполнение из циклов."""
    return tabel_screen.reset(db, principal, payload)
