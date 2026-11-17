"""API профилей гостей (§3.2, §8): список с фамилиями — stays.view, карточка целиком —
stays.guests, запись — stays.edit. Батлер (часть 4 §3) — только свои гости: чтение — stays.mine,
профиль, пожелания и связи — stays.mine_guest_edit. Изменения — в журнале аудита с разницей полей.
Вкладка «Гости» (addendum §3): справочник с фильтрами, история проживаний, объединение дублей.

Правила — в прикладном слое: ``guest_screen`` (чтение), ``guest_edit`` (запись), ``guest_access``
(кто что видит и правит). Роутер разбирает запрос и проверяет право эндпоинта.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.core.schemas import Ok

from ..adapters.duty_timesheet import TimesheetDuty
from ..application import guest_edit, guest_screen, guests_list
from ..application.guest_forms import FormerIn, GuestIn, GuestUpdateIn, LinkIn, MergeIn, PrefsIn
from ._ops import PREVIEW
from .schemas import (
    FamilyOut,
    GuestCardOut,
    GuestLinkCreatedOut,
    GuestLinkFormerOut,
    GuestMergedOut,
    GuestPickOut,
    GuestPrefOut,
    GuestPrefsSavedOut,
    GuestStayOut,
    GuestTabOut,
    GuestUpdatedOut,
)

router = APIRouter(prefix="/api/stays", tags=["stays"])


@router.get("/guests", response_model=list[GuestPickOut])
def list_guests(q: str = "", mine_only: bool = Query(False, alias="mine"),
                principal: Principal = Depends(require_perm("stays.view")), db: Session = Depends(get_db)):
    """Подбор гостя; mine=1 — только свои гости батлера (редактор связей, часть 4 §3)."""
    return guest_screen.search(db, principal, q, mine_only)


@router.get("/guests/list", response_model=GuestTabOut)
def guests_tab(q: str = "", special: bool = False, vip_code_id: Optional[int] = None,
               stayed_from: Optional[dt.date] = None, stayed_to: Optional[dt.date] = None,
               birthday_days: Optional[int] = Query(None, ge=0, le=guests_list.MAX_BIRTHDAY_DAYS),
               sort: Literal["name", "special", "last_stay", "stays"] = "name", dir: Literal["asc", "desc"] = "asc",
               offset: int = Query(0, ge=0), limit: int = Query(guests_list.MAX_LIMIT, ge=1, le=guests_list.MAX_LIMIT),
               principal: Principal = Depends(require_perm("stays.guests")), db: Session = Depends(get_db)):
    """Вкладка «Гости»: только полный уровень (stays.guests), остальным — 403."""
    return guest_screen.tab(db, principal, q=q, special=special, vip_code_id=vip_code_id,
                            stayed_from=stayed_from, stayed_to=stayed_to, birthday_days=birthday_days,
                            sort=sort, direction=dir, offset=offset, limit=limit)


@router.post("/guests/merge", response_model=GuestMergedOut)
def merge_guests(payload: MergeIn, preview_flag: bool = PREVIEW,
                 principal: Principal = Depends(require_perm("stays.edit")), db: Session = Depends(get_db)):
    """Объединение дублей: ?preview=1 — что перенесётся, тем же кодом с откатом."""
    return guest_edit.merge(db, principal, payload, preview_only=preview_flag)


@router.get("/guests/{gid}", response_model=GuestCardOut)
def get_guest(gid: int, principal: Principal = Depends(require_perm("stays.guests", "stays.mine")),
              db: Session = Depends(get_db)):
    return guest_screen.get_card(db, principal, gid)


@router.get("/guests/{gid}/stays", response_model=list[GuestStayOut])
def guest_stays(gid: int, principal: Principal = Depends(require_perm("stays.guests")),
                db: Session = Depends(get_db)):
    """История проживаний гостя: все брони, где он жил, с объектами по фонду дня и батлерами."""
    return guest_screen.stays_of(db, principal, gid)


@router.get("/guests/{gid}/prefs", response_model=list[GuestPrefOut])
def guest_prefs(gid: int, principal: Principal = Depends(require_perm("stays.guests", "stays.mine")),
                db: Session = Depends(get_db)):
    """Пожелания гостя к объекту (часть 2 §5): полный уровень или свой гость батлера."""
    return guest_screen.prefs(db, principal, gid)


@router.put("/guests/{gid}/prefs", response_model=GuestPrefsSavedOut)
def set_guest_prefs(gid: int, payload: PrefsIn, preview_flag: bool = PREVIEW,
                    principal: Principal = Depends(require_perm("stays.edit", "stays.mine_guest_edit")),
                    db: Session = Depends(get_db)):
    """Заменить пожелания гостя целиком; ?preview=1 показывает, кто из броней переедет."""
    return guest_edit.set_prefs(db, principal, gid, payload, preview_only=preview_flag)


@router.post("/guests", response_model=GuestCardOut)
def create_guest(payload: GuestIn, principal: Principal = Depends(require_perm("stays.edit")),
                 db: Session = Depends(get_db)):
    return guest_edit.create(db, principal, payload)


@router.put("/guests/{gid}", response_model=GuestUpdatedOut)
def update_guest(gid: int, payload: GuestUpdateIn, preview_flag: bool = PREVIEW,
                 principal: Principal = Depends(require_perm("stays.edit", "stays.mine_guest_edit")),
                 db: Session = Depends(get_db)):
    """Правка профиля; смена кода переходит в текущие и будущие брони, где гость главный."""
    return guest_edit.update(db, principal, gid, payload, preview_only=preview_flag, duty=TimesheetDuty(db))


@router.post("/guests/{gid}/links", response_model=GuestLinkCreatedOut)
def create_link(gid: int, payload: LinkIn,
                principal: Principal = Depends(require_perm("stays.edit", "stays.mine_guest_edit")),
                db: Session = Depends(get_db)):
    """Связь, при необходимости — с новым гостем и вторым родителем; отказ — ничего не создаётся."""
    return guest_edit.add_link(db, principal, gid, payload)


@router.get("/guests/{gid}/family", response_model=FamilyOut)
def guest_family(gid: int, principal: Principal = Depends(require_perm("stays.view", "stays.occupancy")),
                 db: Session = Depends(get_db)):
    """Семейное дерево (§4): уровень «с фамилиями» и выше."""
    return guest_screen.family(db, principal, gid)


@router.patch("/guest-links/{link_id}", response_model=GuestLinkFormerOut)
def set_link_former(link_id: int, payload: FormerIn,
                    principal: Principal = Depends(require_perm("stays.edit", "stays.mine_guest_edit")),
                    db: Session = Depends(get_db)):
    """«Бывшие» на линии супругов в редакторе дерева."""
    return guest_edit.set_link_former(db, principal, link_id, payload)


@router.delete("/guest-links/{link_id}", response_model=Ok)
def remove_link(link_id: int, principal: Principal = Depends(require_perm("stays.edit", "stays.mine_guest_edit")),
                db: Session = Depends(get_db)):
    """Батлер — если хотя бы одна сторона связи своя."""
    return guest_edit.remove_link(db, principal, link_id)
