"""API блоков (часть 2 §3.2, §6, §7): сетка «категория × ночь → остаток», помощник «заполнить» и
быстрая правка. Список и карточку видят все уровни (персональных данных в блоках нет); запись —
stays.edit, с предпросмотром, версией (409) и журналом «было → стало».

Правила — в прикладном слое: ``application/block_edit.py``. Роутер разбирает запрос и проверяет право.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..adapters.duty_timesheet import TimesheetDuty
from ..application import block_edit, blocks
from ..application.block_edit import BlockIn, BlockPut, NightsIn
from ._ops import PREVIEW
from .schemas import BlockCardOut, BlockListOut, BlockSavedOut, DeletedOut, PreviewedOut

router = APIRouter(prefix="/api/stays", tags=["stays"])
EDIT = require_perm("stays.edit")
SEE = require_perm("stays.view", "stays.occupancy")


def _query(first: Optional[dt.date] = None, last: Optional[dt.date] = None,
           category_ids: list[int] = Query(default=[]), short_only: bool = False, q: str = "", sort: str = "start",
           dir: Literal["asc", "desc"] = "asc", offset: int = Query(0, ge=0),
           limit: int = Query(blocks.MAX_LIMIT, ge=1, le=blocks.MAX_LIMIT)) -> blocks.BlockQuery:
    return blocks.BlockQuery(first, last, tuple(category_ids), short_only, q, sort, dir, offset, limit)


@router.get("/blocks", response_model=BlockListOut)
def blocks_list(query: blocks.BlockQuery = Depends(_query), principal: Principal = Depends(SEE),
                db: Session = Depends(get_db)):
    return blocks.list_blocks(db, query)


@router.get("/blocks/{bid}", response_model=BlockCardOut)
def block_get(bid: int, principal: Principal = Depends(SEE), db: Session = Depends(get_db)):
    return block_edit.card(db, bid)


@router.post("/blocks", response_model=PreviewedOut[BlockSavedOut])
def create_block(payload: BlockIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
                 db: Session = Depends(get_db)):
    return block_edit.save(db, principal, payload, None, preview_only=preview_flag, duty=TimesheetDuty(db))


@router.put("/blocks/{bid}", response_model=PreviewedOut[BlockSavedOut])
def update_block(bid: int, payload: BlockPut, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
                 db: Session = Depends(get_db)):
    return block_edit.save(db, principal, payload, bid, preview_only=preview_flag, duty=TimesheetDuty(db))


@router.patch("/blocks/{bid}/nights", response_model=PreviewedOut[BlockSavedOut])
def block_nights(bid: int, payload: NightsIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
                 db: Session = Depends(get_db)):
    return block_edit.set_nights(db, principal, bid, payload, preview_only=preview_flag, duty=TimesheetDuty(db))


@router.delete("/blocks/{bid}", response_model=PreviewedOut[DeletedOut])
def remove_block(bid: int, version: int, preview_flag: bool = PREVIEW, principal: Principal = Depends(EDIT),
                 db: Session = Depends(get_db)):
    return block_edit.remove(db, principal, bid, version, preview_only=preview_flag, duty=TimesheetDuty(db))
