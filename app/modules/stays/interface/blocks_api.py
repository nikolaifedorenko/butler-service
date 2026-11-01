"""API блоков (часть 2 §3.2, §6, §7): сетка «категория × ночь → остаток», помощник «заполнить» и
быстрая правка. Список и карточку видят все уровни (персональных данных в блоках нет); запись —
stays.edit, с предпросмотром через общий run_operation, версией (409) и журналом «было → стало»."""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..adapters.orm import Block
from ..application import blocks, views
from ..application.fund import changes
from ..application.preview import change_window
from ._ops import PREVIEW, run
from .views_api import SEE

router = APIRouter(prefix="/api/stays", tags=["stays"])
EDIT = require_perm("stays.edit")


def _sane(v: dt.date) -> dt.date:
    if not dt.date(2000, 1, 1) <= v <= dt.date(2200, 12, 31):
        raise ValueError("дата вне допустимого диапазона 2000–2200")
    return v


class BlockIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    start: dt.date
    end: dt.date
    grid: dict[int, dict[dt.date, int]] = {}         # категория → ночь → остаток (целиком)

    _dates = field_validator("start", "end")(_sane)


class BlockPut(BlockIn):
    grid: Optional[dict[int, dict[dt.date, int]]] = None   # не передана — прежняя сетка, ночи вне дат уходят
    version: int


class NightsIn(BaseModel):
    version: int
    category_id: int
    first: dt.date                                   # первая и последняя ночи включительно
    last: dt.date
    quantity: int = Field(ge=0, le=blocks.MAX_QUANTITY)      # 0 — убрать ночи
    _dates = field_validator("first", "last")(_sane)


def _query(first: Optional[dt.date] = None, last: Optional[dt.date] = None,
           category_ids: list[int] = Query(default=[]), short_only: bool = False, q: str = "", sort: str = "start",
           dir: Literal["asc", "desc"] = "asc", offset: int = Query(0, ge=0),
           limit: int = Query(blocks.MAX_LIMIT, ge=1, le=blocks.MAX_LIMIT)) -> blocks.BlockQuery:
    try:
        return blocks.BlockQuery(first, last, tuple(category_ids), short_only, q, sort, dir, offset, limit)
    except views.ViewError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _found(db: Session, bid: int) -> Block:
    b = db.get(Block, bid)
    if b is None:
        raise HTTPException(status_code=404, detail="Блок не найден")
    return b


def _audit(db: Session, principal: Principal, bid: int, before: dict, after: dict) -> None:
    audit(db, principal, "stays_block", f"block:{bid}", {"diff": changes(before, after)})


def _save_op(db: Session, principal: Principal, payload: BlockIn, bid: Optional[int]):
    def op():
        b, before, dropped = blocks.save_block(db, payload.model_dump(), bid, principal.user.id)
        after = blocks.block_dict(db, b)
        _audit(db, principal, b.id, before, after)
        return {**after, "dropped": dropped}
    return op


@router.get("/blocks")
def blocks_list(query: blocks.BlockQuery = Depends(_query), principal: Principal = Depends(SEE),
                db: Session = Depends(get_db)):
    return blocks.list_blocks(db, query)


@router.get("/blocks/{bid}")
def block_get(bid: int, principal: Principal = Depends(SEE), db: Session = Depends(get_db)):
    _found(db, bid)
    return blocks.block_card(db, bid)


@router.post("/blocks")
def create_block(payload: BlockIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
                 db: Session = Depends(get_db)):
    window = change_window((payload.start, max(payload.end - dt.timedelta(days=1), payload.start)))
    return run(db, _save_op(db, principal, payload, None), preview_flag, window, principal)


@router.put("/blocks/{bid}")
def update_block(bid: int, payload: BlockPut, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
                 db: Session = Depends(get_db)):
    b = _found(db, bid)
    window = change_window((payload.start, max(payload.end - dt.timedelta(days=1), payload.start)),
                           (b.start, b.end - dt.timedelta(days=1)))
    return run(db, _save_op(db, principal, payload, bid), preview_flag, window, principal)


@router.patch("/blocks/{bid}/nights")
def block_nights(bid: int, payload: NightsIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
                 db: Session = Depends(get_db)):
    _found(db, bid)

    def op():
        b, before = blocks.set_nights(db, bid, payload.version, payload.category_id, payload.first, payload.last,
                                      payload.quantity)
        after = blocks.block_dict(db, b)
        _audit(db, principal, bid, before, after)
        return after
    return run(db, op, preview_flag, change_window((payload.first, max(payload.last, payload.first))), principal)


@router.delete("/blocks/{bid}")
def remove_block(bid: int, version: int, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
                 db: Session = Depends(get_db)):
    b = _found(db, bid)

    def op():
        before = blocks.delete_block(db, bid, version)
        _audit(db, principal, bid, before, {k: None for k in before})
        return {"id": bid, "deleted": True}
    return run(db, op, preview_flag, change_window((b.start, b.end - dt.timedelta(days=1))), principal)
