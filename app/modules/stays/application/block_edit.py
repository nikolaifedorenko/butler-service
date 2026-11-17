"""Блоки (часть 2 §3.2, §6, §7): сетка «категория × ночь → остаток», помощник «заполнить» и быстрая правка.

Список и карточку видят все уровни (персональных данных в блоках нет); запись — ``stays.edit``,
с предпросмотром, версией (409) и журналом «было → стало».
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.errors import NotFound

from ..adapters.orm import Block
from ..ports.duty import DutyPort
from . import blocks
from .fund import changes
from .preview import change_window
from .previewed import run_previewed


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


def _found(db: Session, bid: int) -> Block:
    b = db.get(Block, bid)
    if b is None:
        raise NotFound("Блок не найден")
    return b


def _audit(db: Session, principal: Principal, bid: int, before: dict, after: dict) -> None:
    audit(db, principal, "stays_block", f"block:{bid}", {"diff": changes(before, after)})


def _may_overbook(principal: Principal) -> bool:
    return "stays.overbook" in principal.gate_permissions


def card(db: Session, bid: int) -> dict:
    _found(db, bid)
    return blocks.block_card(db, bid)


def save(db: Session, principal: Principal, payload: BlockIn, bid: int | None, *, preview_only: bool,
         duty: DutyPort | None = None) -> dict:
    """Создать блок (``bid`` пуст) или заменить; предпросмотр — тот же код с откатом."""
    new_range = (payload.start, max(payload.end - dt.timedelta(days=1), payload.start))
    if bid is None:
        window = change_window(new_range)
    else:
        b = _found(db, bid)
        window = change_window(new_range, (b.start, b.end - dt.timedelta(days=1)))

    def operation():
        b, before, dropped = blocks.save_block(db, payload.model_dump(), bid, principal.user.id)
        after = blocks.block_dict(db, b)
        _audit(db, principal, b.id, before, after)
        return {**after, "dropped": dropped}
    return run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal),
                         window=window, duty=duty)


def set_nights(db: Session, principal: Principal, bid: int, payload: NightsIn, *, preview_only: bool,
               duty: DutyPort | None = None) -> dict:
    _found(db, bid)

    def operation():
        b, before = blocks.set_nights(db, bid, payload.version, payload.category_id, payload.first,
                                      payload.last, payload.quantity)
        after = blocks.block_dict(db, b)
        _audit(db, principal, bid, before, after)
        return {**after, "dropped": None}
    return run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal),
                         window=change_window((payload.first, max(payload.last, payload.first))), duty=duty)


def remove(db: Session, principal: Principal, bid: int, version: int, *, preview_only: bool,
           duty: DutyPort | None = None) -> dict:
    b = _found(db, bid)

    def operation():
        before = blocks.delete_block(db, bid, version)
        _audit(db, principal, bid, before, {k: None for k in before})
        return {"id": bid, "deleted": True}
    return run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal),
                         window=change_window((b.start, b.end - dt.timedelta(days=1))), duty=duty)
