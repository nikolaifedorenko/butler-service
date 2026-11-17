"""OOO (часть 2 §3.1, §6, §7): объект не в продаже по половинкам суток.

Список видят все уровни (персональных данных в OOO нет); запись — ``stays.edit``, с
предпросмотром, оптимистической версией (409) и журналом «было → стало».
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.errors import NotFound

from ..adapters.orm import Ooo
from ..ports.duty import DutyPort
from . import ooo
from .fund import changes
from .preview import change_window
from .previewed import run_previewed


class OooIn(BaseModel):
    unit_id: int
    start: dt.date
    end: dt.date
    start_half: Literal["AM", "PM"] = "PM"          # «с» — с вечера дня выезда; «с утра» — AM
    end_half: Literal["AM", "PM"] = "AM"            # «по» — до утра дня заезда; «до вечера» — PM
    reason: str = Field("", max_length=120)

    @field_validator("start", "end")
    @classmethod
    def _sane(cls, v: dt.date) -> dt.date:
        if not dt.date(2000, 1, 1) <= v <= dt.date(2200, 12, 31):
            raise ValueError("дата вне допустимого диапазона 2000–2200")
        return v


class OooPut(OooIn):
    version: int


def _found(db: Session, oid: int) -> Ooo:
    o = db.get(Ooo, oid)
    if o is None:
        raise NotFound("OOO не найден")
    return o


def _may_overbook(principal: Principal) -> bool:
    return "stays.overbook" in principal.gate_permissions


def save(db: Session, principal: Principal, payload: OooIn, oid: int | None, *, preview_only: bool,
         duty: DutyPort | None = None) -> dict:
    """Создать OOO (``oid`` пуст) или заменить; предпросмотр — тот же код с откатом."""
    if oid is None:
        window = change_window((payload.start, payload.end))
    else:
        o = _found(db, oid)
        window = change_window((payload.start, payload.end), (o.start, o.end))

    def operation():
        o, before = ooo.save_ooo(db, payload.model_dump(), oid, principal.user.id)
        after = ooo.ooo_dict(o)
        audit(db, principal, "stays_ooo", f"ooo:{o.id}", {"diff": changes(before, after)})
        return after
    return run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal),
                         window=window, duty=duty)


def remove(db: Session, principal: Principal, oid: int, version: int, *, preview_only: bool,
           duty: DutyPort | None = None) -> dict:
    o = _found(db, oid)

    def operation():
        before = ooo.delete_ooo(db, oid, version)
        audit(db, principal, "stays_ooo", f"ooo:{oid}", {"diff": changes(before, {k: None for k in before})})
        return {"id": oid, "deleted": True}
    return run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal),
                         window=change_window((o.start, o.end)), duty=duty)
