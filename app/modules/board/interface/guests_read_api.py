"""API чтения профилей гостей (§3.2, §4, §8): подбор с фамилиями — stays.view, карточка целиком и
раздел «Гости» — stays.guests, батлеру — свои гости (stays.mine). Запись профилей, связей и пожеланий —
в stays: она пересчитывает размещение.

Правила — в прикладном слое: ``application/guest_screen.py``. Роутер разбирает запрос и проверяет право.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.modules.guests.application.guest_schemas import GuestCardOut, GuestPrefOut  # noqa: F401
from app.modules.stays.application import guests_list

from ..application import guest_screen
from .schemas import FamilyOut, GuestPickOut, GuestStayOut, GuestTabOut

router = APIRouter(prefix="/api/stays", tags=["stays"])


@router.get("/guests", response_model=list[GuestPickOut], response_model_exclude_unset=True)
def list_guests(q: str = "", mine_only: bool = Query(False, alias="mine"), details: bool = False,
                principal: Principal = Depends(require_perm("stays.view", "stays.guests", "stays.mine_guest_edit")),
                db: Session = Depends(get_db)):
    """Подбор гостя; mine=1 — только свои гости батлера (редактор связей, часть 4 §3)."""
    if "stays.view" not in principal.gate_permissions and "stays.guests" not in principal.gate_permissions:
        mine_only = True
    return guest_screen.search(db, principal, q, mine_only, details=details)


@router.get("/guests/list", response_model=GuestTabOut)
def guests_tab(q: str = "", special: bool = False, vip_code_id: Optional[int] = None,
               stayed_from: Optional[dt.date] = None, stayed_to: Optional[dt.date] = None,
               birthday_days: Optional[int] = Query(None, ge=0, le=guests_list.MAX_BIRTHDAY_DAYS),
               sort: Literal["name", "special", "last_stay", "stays"] = "name", dir: Literal["asc", "desc"] = "asc",
               offset: int = Query(0, ge=0), limit: int = Query(guests_list.MAX_LIMIT, ge=1, le=guests_list.MAX_LIMIT),
               principal: Principal = Depends(require_perm("stays.guests")), db: Session = Depends(get_db)):
    """Раздел «Гости»: только полный уровень (stays.guests), остальным — 403."""
    return guest_screen.tab(db, principal, q=q, special=special, vip_code_id=vip_code_id,
                            stayed_from=stayed_from, stayed_to=stayed_to, birthday_days=birthday_days,
                            sort=sort, direction=dir, offset=offset, limit=limit)


@router.get("/guests/{gid}", response_model=GuestCardOut)
def get_guest(gid: int, principal: Principal = Depends(require_perm("stays.guests", "stays.mine", "stays.mine_guest_edit")),
              db: Session = Depends(get_db)):
    return guest_screen.get_card(db, principal, gid)


@router.get("/guests/{gid}/stays", response_model=list[GuestStayOut])
def guest_stays(gid: int, principal: Principal = Depends(require_perm("stays.guests")),
                db: Session = Depends(get_db)):
    """История проживаний гостя: все брони, где он жил, с объектами по фонду дня и батлерами."""
    return guest_screen.stays_of(db, principal, gid)


@router.get("/guests/{gid}/prefs", response_model=list[GuestPrefOut])
def guest_prefs(gid: int, principal: Principal = Depends(require_perm("stays.guests", "stays.mine", "stays.mine_guest_edit")),
                db: Session = Depends(get_db)):
    """Пожелания гостя к объекту (часть 2 §5): полный уровень или свой гость батлера."""
    return guest_screen.prefs(db, principal, gid)


@router.get("/guests/{gid}/family", response_model=FamilyOut)
def guest_family(gid: int, principal: Principal = Depends(require_perm("stays.view", "stays.occupancy", "stays.guests", "stays.mine", "stays.mine_guest_edit")),
                 db: Session = Depends(get_db)):
    """Семейное дерево (§4): уровень «с фамилиями» и выше."""
    return guest_screen.family(db, principal, gid)


