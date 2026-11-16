"""API вкладки «Отметки» — доска «прямо сейчас» (16.2). Правила — в ``application/presence_screen.py``."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..application import presence_screen
from .schemas import PresenceBoardOut

router = APIRouter(prefix="/api/presence", tags=["presence"])


@router.get("/board", response_model=PresenceBoardOut)
def board(principal: Principal = Depends(require_perm("presence.view")),
          db: Session = Depends(get_db)):
    """Кто на работе, кто ожидается, открытые сессии и кто ещё должен прийти."""
    return presence_screen.board(db, principal)
