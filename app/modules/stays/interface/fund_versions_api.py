"""API версий фонда (спецификация stays-fund-versions §4, §6): снимок на дату и черновик.

Чтение — тем, кто видит шахматку (READ), запись — правом stays.setup. Каждая запись черновика
несёт rev (оптимистичная блокировка: 409 при расхождении) и возвращает новый rev."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.identity import User

from ..adapters.orm import FundVersion, UnitFlag
from ..application import fund_drafts as fd
from ..application.fund import FundError
from ..application.fund_versions import FundSnapshot, fund_on, snapshot_of
from .fund_api import READ, SETUP, SORT, CategoryIn, _err

router = APIRouter(prefix="/api/stays", tags=["stays"])


# ── тела запросов ──────────────────────────────────────────────────────────


class DraftIn(BaseModel):
    valid_from: dt.date
    note: str = Field("", max_length=500)


class DraftMoveIn(BaseModel):
    rev: int
    valid_from: dt.date


class RevIn(BaseModel):
    rev: int


class DraftCategoryIn(CategoryIn):
    rev: int


class DraftGroupIn(BaseModel):
    rev: int
    title: str = Field(min_length=1, max_length=120)
    parent_id: Optional[int] = None
    sort_order: int = SORT


class UnitFields(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    category_id: int
    group_id: Optional[int] = None
    floor: str = Field("", max_length=8)


class DraftUnitIn(UnitFields):
    rev: int
    flags: list[int] = []


class PartIn(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    category_id: Optional[int] = None
    group_id: Optional[int] = None
    floor: str = Field("", max_length=8)


class SplitIn(BaseModel):
    rev: int
    parts: list[PartIn] = Field(min_length=2, max_length=50)


class MergeIn(BaseModel):
    rev: int
    unit_ids: list[int] = Field(min_length=2, max_length=50)
    label: str = Field(min_length=1, max_length=40)
    category_id: Optional[int] = None
    group_id: Optional[int] = None
    floor: str = Field("", max_length=8)


class FlagValueIn(BaseModel):
    rev: int
    flag_id: int
    unit_ids: list[int] = Field(max_length=500)
    value: bool


class FlagIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    title: str = Field(min_length=1, max_length=80)
    color: str = "#3b6fd8"
    sort_order: int = SORT

    @field_validator("color")
    @classmethod
    def _hex(cls, v: str) -> str:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise ValueError("Цвет в формате #RRGGBB")
        return v


class ArchiveIn(BaseModel):
    archived: bool


# ── чтение ─────────────────────────────────────────────────────────────────


def _version_dict(v: FundVersion) -> dict:
    return {"id": v.id, "valid_from": v.valid_from.isoformat(), "status": v.status, "rev": v.rev}


def _snapshot_dict(db: Session, version: FundVersion, snap: FundSnapshot) -> dict:
    return {
        "version": _version_dict(version),
        "categories": [{"id": c.id, "code": c.code, "title": c.title, "kind": c.kind, "weight": c.weight,
                        "escorted": c.escorted, "sort_order": c.sort_order}
                       for c in sorted(snap.categories.values(), key=lambda c: (c.sort_order, c.id))],
        "groups": [{"id": g.id, "parent_id": g.parent_id, "title": g.title, "sort_order": g.sort_order,
                    "path": list(g.path)}
                   for g in sorted(snap.groups.values(), key=lambda g: (g.sort_order, g.id))],
        "units": [{"id": u.id, "label": u.label, "category_id": u.category_id, "group_id": u.group_id,
                   "floor": u.floor, "flags": sorted(u.flags),
                   "path": list(snap.groups[u.group_id].path) if u.group_id in snap.groups else []}
                  for u in sorted(snap.units.values(), key=lambda u: (u.label, u.id))],
        "flags": [{"id": f.id, "title": f.title, "color": f.color, "sort_order": f.sort_order,
                   "archived": f.archived}
                  for f in db.scalars(select(UnitFlag).order_by(UnitFlag.sort_order, UnitFlag.id))],
    }


@router.get("/fund/snapshot")
def get_snapshot(date: Optional[dt.date] = None, version_id: Optional[int] = None,
                 principal: Principal = Depends(READ), db: Session = Depends(get_db)):
    if (date is None) == (version_id is None):
        raise HTTPException(422, "Укажите ровно один параметр: date или version_id")
    if version_id is not None:
        version = db.get(FundVersion, version_id)
        if version is None:
            raise HTTPException(404, "Версии фонда нет")
        snap = snapshot_of(db, version_id)
    else:
        snap = fund_on(db, date)
        version = db.get(FundVersion, snap.version_id)
    return _snapshot_dict(db, version, snap)


@router.get("/fund/versions")
def list_versions(principal: Principal = Depends(READ), db: Session = Depends(get_db)):
    rows = db.execute(select(FundVersion, User.username)
                      .outerjoin(User, User.id == FundVersion.author_id)
                      .order_by(FundVersion.valid_from, FundVersion.id)).all()
    return [{"id": v.id, "valid_from": v.valid_from.isoformat(), "status": v.status, "author": name,
             "note": v.note, "published_at": v.published_at.isoformat() if v.published_at else None}
            for v, name in rows]


@router.get("/fund/draft/diff")
def draft_diff(principal: Principal = Depends(READ), db: Session = Depends(get_db)):
    draft = fd.current_draft(db)
    if draft is None:
        raise HTTPException(422, "Черновика фонда нет")
    if draft.base_version_id is None:
        return asdict(fd.FundDiff())
    return asdict(fd.diff(db, draft.base_version_id, draft.id))


# ── запись черновика ───────────────────────────────────────────────────────


def _done(db: Session, principal: Principal, target: str, payload: dict, **extra) -> dict:
    """Журнал и commit; ответ — новый rev черновика и результат действия."""
    draft = fd.current_draft(db)
    audit(db, principal, "stays_fund_version", target, payload)
    out = {"rev": draft.rev if draft else None, **extra}
    db.commit()
    return out


def _run(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except FundError as e:
        raise _err(e) from e


@router.post("/fund/draft")
def open_draft(payload: DraftIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    d = _run(fd.open_draft, db, payload.valid_from, principal.user.id, payload.note)
    return _done(db, principal, f"fund_draft:{d.id}", {"open": payload.valid_from.isoformat()},
                 id=d.id, valid_from=d.valid_from.isoformat())


@router.patch("/fund/draft")
def move_draft(payload: DraftMoveIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    _run(fd.move_draft_date, db, payload.rev, payload.valid_from)
    return _done(db, principal, "fund_draft", {"move": payload.valid_from.isoformat()},
                 valid_from=payload.valid_from.isoformat())


@router.delete("/fund/versions/{vid}")
def remove_version(vid: int, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    _run(fd.delete_version, db, vid)
    audit(db, principal, "stays_fund_version", f"fund_version:{vid}", {"delete": True})
    db.commit()
    return {"ok": True}


def _data(payload: BaseModel) -> dict:
    return payload.model_dump(exclude={"rev"}, exclude_unset=True)


@router.post("/fund/draft/categories")
def create_category(payload: DraftCategoryIn, principal: Principal = Depends(SETUP),
                    db: Session = Depends(get_db)):
    cid = _run(fd.save_category, db, payload.rev, _data(payload), None)
    return _done(db, principal, f"fund_draft:category:{cid}", {"save": _data(payload)}, id=cid)


@router.put("/fund/draft/categories/{cid}")
def update_category(cid: int, payload: DraftCategoryIn, principal: Principal = Depends(SETUP),
                    db: Session = Depends(get_db)):
    _run(fd.save_category, db, payload.rev, _data(payload), cid)
    return _done(db, principal, f"fund_draft:category:{cid}", {"save": _data(payload)}, id=cid)


@router.delete("/fund/draft/categories/{cid}")
def remove_category(cid: int, rev: int = Query(), principal: Principal = Depends(SETUP),
                    db: Session = Depends(get_db)):
    _run(fd.retire_category, db, rev, cid)
    return _done(db, principal, f"fund_draft:category:{cid}", {"retire": True})


@router.post("/fund/draft/groups")
def create_group(payload: DraftGroupIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    gid = _run(fd.save_group, db, payload.rev, _data(payload), None)
    return _done(db, principal, f"fund_draft:group:{gid}", {"save": _data(payload)}, id=gid)


@router.put("/fund/draft/groups/{gid}")
def update_group(gid: int, payload: DraftGroupIn, principal: Principal = Depends(SETUP),
                 db: Session = Depends(get_db)):
    _run(fd.save_group, db, payload.rev, _data(payload), gid)
    return _done(db, principal, f"fund_draft:group:{gid}", {"save": _data(payload)}, id=gid)


@router.delete("/fund/draft/groups/{gid}")
def remove_group(gid: int, rev: int = Query(), principal: Principal = Depends(SETUP),
                 db: Session = Depends(get_db)):
    _run(fd.retire_group, db, rev, gid)
    return _done(db, principal, f"fund_draft:group:{gid}", {"retire": True})


@router.post("/fund/draft/units")
def create_unit(payload: DraftUnitIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    uid = _run(fd.save_unit, db, payload.rev, _data(payload), None)
    return _done(db, principal, f"fund_draft:unit:{uid}", {"save": _data(payload)}, id=uid)


@router.put("/fund/draft/units/{uid}")
def update_unit(uid: int, payload: DraftUnitIn, principal: Principal = Depends(SETUP),
                db: Session = Depends(get_db)):
    _run(fd.save_unit, db, payload.rev, _data(payload), uid)
    return _done(db, principal, f"fund_draft:unit:{uid}", {"save": _data(payload)}, id=uid)


@router.delete("/fund/draft/units/{uid}")
def remove_unit(uid: int, rev: int = Query(), principal: Principal = Depends(SETUP),
                db: Session = Depends(get_db)):
    _run(fd.retire_unit, db, rev, uid)
    return _done(db, principal, f"fund_draft:unit:{uid}", {"retire": True})


@router.post("/fund/draft/units/merge")
def merge_units(payload: MergeIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"rev", "unit_ids"}, exclude_unset=True)
    new_id = _run(fd.merge_units, db, payload.rev, payload.unit_ids, data)
    return _done(db, principal, f"fund_draft:unit:{new_id}",
                 {"merge": payload.unit_ids, "into": data}, id=new_id)


@router.post("/fund/draft/units/{uid}/split")
def split_unit(uid: int, payload: SplitIn, principal: Principal = Depends(SETUP),
               db: Session = Depends(get_db)):
    parts = [p.model_dump(exclude_unset=True) for p in payload.parts]
    ids = _run(fd.split_unit, db, payload.rev, uid, parts)
    return _done(db, principal, f"fund_draft:unit:{uid}", {"split": parts, "into": ids}, ids=ids)


@router.put("/fund/draft/flags")
def put_draft_flags(payload: FlagValueIn, principal: Principal = Depends(SETUP),
                    db: Session = Depends(get_db)):
    _run(fd.set_flag, db, payload.rev, payload.flag_id, payload.unit_ids, payload.value)
    return _done(db, principal, f"fund_draft:flag:{payload.flag_id}",
                 {"units": payload.unit_ids, "value": payload.value})


@router.post("/fund/draft/publish")
def publish_draft(payload: RevIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    version = _run(fd.publish, db, principal, payload.rev)
    out = {"id": version.id, "valid_from": version.valid_from.isoformat(), "rev": version.rev}
    db.commit()
    return out


# ── справочник флагов (вне черновика) ──────────────────────────────────────


def _flag_done(db: Session, principal: Principal, flag_id: int, payload: dict) -> dict:
    audit(db, principal, "stays_fund", f"flag:{flag_id}", payload)
    db.commit()
    return {"id": flag_id}


@router.post("/fund/flags")
def create_flag(payload: FlagIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    fid = _run(fd.save_flag, db, payload.model_dump(), None)
    return _flag_done(db, principal, fid, payload.model_dump())


@router.put("/fund/flags/{fid}")
def update_flag(fid: int, payload: FlagIn, principal: Principal = Depends(SETUP),
                db: Session = Depends(get_db)):
    _run(fd.save_flag, db, payload.model_dump(), fid)
    return _flag_done(db, principal, fid, payload.model_dump())


@router.put("/fund/flags/{fid}/archive")
def archive_flag(fid: int, payload: ArchiveIn, principal: Principal = Depends(SETUP),
                 db: Session = Depends(get_db)):
    _run(fd.archive_flag, db, fid, payload.archived)
    return _flag_done(db, principal, fid, {"archived": payload.archived})


@router.delete("/fund/flags/{fid}")
def remove_flag(fid: int, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    _run(fd.delete_flag, db, fid)
    return _flag_done(db, principal, fid, {"delete": True})
