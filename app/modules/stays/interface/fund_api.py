"""API справочников «Шахматки» (§3.1, §3.5, §6 «Экраны Настроек»): метки, настраиваемые поля,
сопровождающие, настройки, VIP-коды. Категории, узлы и объекты фонда живут в версиях —
fund_versions_api. Чтение — тем, кто видит шахматку (в том числе без персональных данных),
запись — правом stays.setup.

Правила — в прикладном слое: ``application/stays_directories.py``. Роутер разбирает запрос и
проверяет право.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import has_perm, require_perm
from app.core.schemas import Ok

from ..application import stays_directories as directories
from ..application.fund_forms import (
    EscortIn,
    FieldIn,
    LabelIn,
    SeedIn,
    SettingsIn,
    VipCodeArchiveIn,
    VipCodeIn,
)
from .schemas import (
    CustomFieldOut,
    EscortChangedOut,
    EscortsSeededOut,
    IdOut,
    LabelOut,
    StaysDirectoriesOut,
    StaysSettingsOut,
    VipCodeOut,
)

router = APIRouter(prefix="/api/stays", tags=["stays"])

# батлеру (stays.mine) — ради определений настраиваемых полей: данных гостей здесь нет
READ = require_perm("stays.view", "stays.occupancy", "stays.setup", "stays.mine")
SETUP = require_perm("stays.setup")


@router.get("/fund", response_model=StaysDirectoriesOut)
def get_fund(principal: Principal = Depends(READ), db: Session = Depends(get_db)):
    return directories.overview(db, with_staff=has_perm(db, principal, "stays.setup"))


@router.post("/labels", response_model=LabelOut)
def create_label(payload: LabelIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return directories.save_label(db, principal, payload, None)


@router.put("/labels/{lid}", response_model=LabelOut)
def update_label(lid: int, payload: LabelIn, principal: Principal = Depends(SETUP),
                 db: Session = Depends(get_db)):
    return directories.save_label(db, principal, payload, lid)


@router.delete("/labels/{lid}", response_model=Ok)
def remove_label(lid: int, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return directories.delete_label(db, principal, lid)


@router.post("/fields", response_model=CustomFieldOut)
def create_field(payload: FieldIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return directories.save_field(db, principal, payload, None)


@router.put("/fields/{fid}", response_model=CustomFieldOut)
def update_field(fid: int, payload: FieldIn, principal: Principal = Depends(SETUP),
                 db: Session = Depends(get_db)):
    return directories.save_field(db, principal, payload, fid)


@router.delete("/fields/{fid}", response_model=Ok)
def remove_field(fid: int, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return directories.delete_field(db, principal, fid)


@router.put("/escorts/{employee_id}", response_model=EscortChangedOut)
def put_escort(employee_id: int, payload: EscortIn, principal: Principal = Depends(SETUP),
               db: Session = Depends(get_db)):
    return directories.set_escort(db, principal, employee_id, payload)


@router.post("/escorts/seed", response_model=EscortsSeededOut)
def seed_escorts(payload: SeedIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return directories.seed_escorts(db, principal, payload)


@router.put("/settings", response_model=StaysSettingsOut)
def put_settings(payload: SettingsIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return directories.save_settings(db, principal, payload)


# ── справочник VIP-кодов ─────────────────────────────────────────────────────


@router.post("/vip-codes", response_model=VipCodeOut)
def create_vip_code(payload: VipCodeIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return directories.save_vip_code(db, principal, payload.model_dump(), None)


@router.put("/vip-codes/{cid}", response_model=VipCodeOut)
def update_vip_code(cid: int, payload: VipCodeIn, principal: Principal = Depends(SETUP),
                    db: Session = Depends(get_db)):
    return directories.save_vip_code(db, principal, payload.model_dump(exclude_unset=True), cid)


@router.put("/vip-codes/{cid}/archive", response_model=VipCodeOut)
def archive_vip_code(cid: int, payload: VipCodeArchiveIn, principal: Principal = Depends(SETUP),
                     db: Session = Depends(get_db)):
    return directories.archive_vip_code(db, principal, cid, payload.archived)


@router.delete("/vip-codes/{cid}", response_model=IdOut)
def remove_vip_code(cid: int, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return directories.delete_vip_code(db, principal, cid)
