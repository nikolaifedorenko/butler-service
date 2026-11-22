"""API профилей гостей (§3.2, §8): список с фамилиями — stays.view, карточка целиком —
stays.guests, запись — stays.edit. Батлер (часть 4 §3) — только свои гости: чтение — stays.mine,
профиль, пожелания и связи — stays.mine_guest_edit. Изменения — в журнале аудита с разницей полей.
Вкладка «Гости» (addendum §3): справочник с фильтрами, история проживаний, объединение дублей.

Правила — в прикладном слое: ``guest_screen`` (чтение), ``guest_edit`` (запись), ``guest_access``
(кто что видит и правит). Роутер разбирает запрос и проверяет право эндпоинта.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.core.schemas import Ok
from app.modules.guests.application.guest_forms import FormerIn, GuestIn, GuestUpdateIn, LinkIn, MergeIn, PrefsIn

from ..adapters.duty_timesheet import TimesheetDuty
from ..application import guest_edit
from ._ops import PREVIEW
from .schemas import (
    GuestCardOut,
    GuestLinkCreatedOut,
    GuestLinkFormerOut,
    GuestMergedOut,
    GuestPrefsSavedOut,
    GuestUpdatedOut,
)

router = APIRouter(prefix="/api/stays", tags=["stays"])


@router.post("/guests/merge", response_model=GuestMergedOut)
def merge_guests(payload: MergeIn, preview_flag: bool = PREVIEW,
                 principal: Principal = Depends(require_perm("stays.edit")), db: Session = Depends(get_db)):
    """Объединение дублей: ?preview=1 — что перенесётся, тем же кодом с откатом."""
    return guest_edit.merge(db, principal, payload, preview_only=preview_flag)


@router.put("/guests/{gid}/prefs", response_model=GuestPrefsSavedOut)
def set_guest_prefs(gid: int, payload: PrefsIn, preview_flag: bool = PREVIEW,
                    principal: Principal = Depends(require_perm("stays.edit", "stays.mine_guest_edit")),
                    db: Session = Depends(get_db)):
    """Заменить пожелания гостя целиком; ?preview=1 показывает, кто из броней переедет."""
    return guest_edit.set_prefs(db, principal, gid, payload, preview_only=preview_flag)


@router.post("/guests", response_model=GuestCardOut)
def create_guest(payload: GuestIn, principal: Principal = Depends(require_perm("stays.edit", "stays.mine_guest_edit")),
                 db: Session = Depends(get_db)):
    """Новый гость: менеджер — полный профиль; батлер — без VIP-кода и «особого», гость сразу «свой»."""
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
