"""API справочников «Шахматки» (§3.1, §3.5, §6 «Экраны Настроек»); категории, узлы и объекты фонда
живут в версиях — fund_versions_api. Чтение — тем, кто видит
шахматку (в том числе без персональных данных), запись — правом stays.setup."""
from __future__ import annotations

import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import has_perm, require_perm

from ..adapters.orm import VipCode
from ..application import fund, guests, vip_codes
from ..application.fund import FundConflict, FundError

router = APIRouter(prefix="/api/stays", tags=["stays"])

# батлеру (stays.mine) — ради определений настраиваемых полей: данных гостей здесь нет
READ = require_perm("stays.view", "stays.occupancy", "stays.setup", "stays.mine")
SETUP = require_perm("stays.setup")


def _err(e: FundError) -> HTTPException:
    return HTTPException(status_code=409 if isinstance(e, FundConflict) else 422, detail=str(e))


def _write(db: Session, principal: Principal, target: str, before: dict, after: dict) -> None:
    audit(db, principal, "stays_fund", target, {"diff": fund.changes(before, after)})
    db.commit()


SORT = Field(100, ge=-100_000, le=100_000)


class CategoryIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    code: str = Field(min_length=1, max_length=16)
    title: str = Field(min_length=1, max_length=120)
    kind_id: int                       # вид из справочника видов категорий
    escorted: bool = False
    weight: float = Field(ge=0, le=100)
    sort_order: int = SORT


class LabelIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    color: str

    @field_validator("color")
    @classmethod
    def _hex(cls, v: str) -> str:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise ValueError("Цвет в формате #RRGGBB")
        return v


class FieldIn(BaseModel):
    target: Literal["guest", "reservation"]
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    title: str = Field(min_length=1, max_length=120)
    kind: Literal["text", "choice", "bool", "date"]
    choices: list[str] = []
    searchable: bool = False
    sort_order: int = SORT


class EscortIn(BaseModel):
    active: bool


class VipCodeIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    code: str = Field(max_length=8)           # цифры 1–8: остальное проверяет vip_codes.normalize_code
    title: str = Field("", max_length=80)
    escorted: bool = False
    factor: float = Field(1.0, ge=0.1, le=99)
    sort_order: int = SORT


class VipCodeArchiveIn(BaseModel):
    archived: bool


class SeedIn(BaseModel):
    position: str = Field("батлер", min_length=2, max_length=60)


class SettingsIn(BaseModel):
    # колонки Numeric(5,2): больше 999.99 PostgreSQL не примет; NaN сломал бы сравнения с лимитом
    model_config = ConfigDict(allow_inf_nan=False)

    special_factor: Optional[float] = Field(None, ge=0.1, le=99)
    daily_limit: float = Field(le=999)
    replacement_codes: str = Field("", max_length=120)


@router.get("/fund")
def get_fund(principal: Principal = Depends(READ), db: Session = Depends(get_db)):
    out = fund.list_fund(db, with_staff=has_perm(db, principal, "stays.setup"))
    out["vip_codes"] = [vip_codes.code_dict(c) for c in vip_codes.all_codes(db)]     # и архивные
    return out


def _save(db, principal, kind: str, saver, fields, payload: BaseModel, rid: Optional[int]):
    try:
        row, before = saver(db, payload.model_dump(), rid)
    except FundError as e:
        raise _err(e) from e
    after = fund.field_dict(row) if kind == "field" else fund.as_dict(row, fields)
    if kind == "field" and bool(before.get("searchable")) != after["searchable"]:
        guests.reindex_search(db)          # флаг «искать по полю» меняет состав search_text
    _write(db, principal, f"{kind}:{row.id}", before, after)
    return after


def _delete(db, principal, kind: str, deleter, rid: int):
    try:
        before = deleter(db, rid)
    except FundError as e:
        raise _err(e) from e
    _write(db, principal, f"{kind}:{rid}", before, {k: None for k in before})
    return {"ok": True}


@router.post("/labels")
def create_label(payload: LabelIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return _save(db, principal, "label", fund.save_label, fund.LABEL_FIELDS, payload, None)


@router.put("/labels/{lid}")
def update_label(lid: int, payload: LabelIn, principal: Principal = Depends(SETUP),
                 db: Session = Depends(get_db)):
    return _save(db, principal, "label", fund.save_label, fund.LABEL_FIELDS, payload, lid)


@router.delete("/labels/{lid}")
def remove_label(lid: int, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return _delete(db, principal, "label", fund.delete_label, lid)


@router.post("/fields")
def create_field(payload: FieldIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return _save(db, principal, "field", fund.save_field, fund.FIELD_FIELDS, payload, None)


@router.put("/fields/{fid}")
def update_field(fid: int, payload: FieldIn, principal: Principal = Depends(SETUP),
                 db: Session = Depends(get_db)):
    return _save(db, principal, "field", fund.save_field, fund.FIELD_FIELDS, payload, fid)


@router.delete("/fields/{fid}")
def remove_field(fid: int, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return _delete(db, principal, "field", fund.delete_field, fid)


@router.put("/escorts/{employee_id}")
def put_escort(employee_id: int, payload: EscortIn, principal: Principal = Depends(SETUP),
               db: Session = Depends(get_db)):
    try:
        row = fund.set_escort(db, employee_id, payload.active)
    except FundError as e:
        raise _err(e) from e
    after = {"employee_id": employee_id, "active": row.active}
    _write(db, principal, f"escort:{employee_id}", {}, after)
    return after


@router.post("/escorts/seed")
def seed_escorts(payload: SeedIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    added = fund.seed_escorts_from_positions(db, payload.position)
    _write(db, principal, "escorts:seed", {}, {"added": added})
    return {"added": added}


@router.put("/settings")
def put_settings(payload: SettingsIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    try:
        row, before = fund.save_settings(db, payload.special_factor, payload.daily_limit,
                                         payload.replacement_codes)
    except FundError as e:
        raise _err(e) from e
    after = fund.as_dict(row, fund.SETTINGS_FIELDS)
    _write(db, principal, "settings", before, after)
    return after


# ── справочник VIP-кодов ───────────────────────────────────────────────────


def _code_done(db: Session, principal: Principal, code_id: int, before: dict, after: dict) -> None:
    audit(db, principal, "stays_vip_code", f"vip_code:{code_id}", {"diff": fund.changes(before, after)})
    db.commit()


def _code_run(db: Session, principal: Principal, code_id: Optional[int], action, *args) -> dict:
    """Действие над справочником кодов под аудитом: before/after — словарь кода (пустой у нового
    и удалённого)."""
    row = db.get(VipCode, code_id) if code_id is not None else None
    before = vip_codes.code_dict(row) if row else {}
    try:
        result = action(db, *args)
    except FundError as e:
        db.rollback()
        raise _err(e) from e
    rid = code_id if code_id is not None else result
    after_row = db.get(VipCode, rid)
    after = vip_codes.code_dict(after_row) if after_row else {k: None for k in before}
    _code_done(db, principal, rid, before, after)
    return {"id": rid} if after_row is None else after


@router.post("/vip-codes")
def create_vip_code(payload: VipCodeIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return _code_run(db, principal, None, vip_codes.save_code, payload.model_dump(), None)


@router.put("/vip-codes/{cid}")
def update_vip_code(cid: int, payload: VipCodeIn, principal: Principal = Depends(SETUP),
                    db: Session = Depends(get_db)):
    return _code_run(db, principal, cid, vip_codes.save_code, payload.model_dump(exclude_unset=True), cid)


@router.put("/vip-codes/{cid}/archive")
def archive_vip_code(cid: int, payload: VipCodeArchiveIn, principal: Principal = Depends(SETUP),
                     db: Session = Depends(get_db)):
    return _code_run(db, principal, cid, vip_codes.archive_code, cid, payload.archived)


@router.delete("/vip-codes/{cid}")
def remove_vip_code(cid: int, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return _code_run(db, principal, cid, vip_codes.delete_code, cid)
