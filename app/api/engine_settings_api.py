"""Настройки движка: версии справочников Т1–Т7, Т9, Т-Группы и модификаторы дня Т4."""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal, audit
from ..db import get_db
from ..engine.adapters.settings_codec import from_payload, to_payload
from ..engine.adapters.sql_settings import base_version
from ..engine.domain.settings.defaults import default_settings
from ..engine.domain.settings.types import MODIFIER_NAMES
from ..engine.domain.settings.validate import validate_settings
from ..engine.domain.types.errors import ConfigError
from ..models import DayModifier, EngineSettingsVersion
from ..permissions import require_perm
from .engine_common import domain_error_text

router = APIRouter(prefix="/api/engine-settings", tags=["engine-settings"])
MODIFIER_TITLES = {"double_overtime": "Двойные переработки", "pays_overtime": "Оплачиваются ли переработки",
                   "plan_equals_fact": "План=Факт", "counts_in_ut": "Учитываются ли часы в УТ"}


@router.get("")
def get_settings(on: Optional[dt.date] = None, principal: Principal = Depends(require_perm("settings.view")),
                 db: Session = Depends(get_db)):
    day = on or dt.date.today()
    ver = base_version(db, day)
    payload = json.loads(ver.payload_json) if ver else to_payload(default_settings())
    versions = db.scalars(select(EngineSettingsVersion).order_by(EngineSettingsVersion.valid_from.desc(),
                                                                 EngineSettingsVersion.id.desc()).limit(50))
    return {"active": {"id": ver.id if ver else None, "valid_from": ver.valid_from.isoformat() if ver else None,
                       "payload": payload},
            "versions": [{"id": v.id, "valid_from": v.valid_from.isoformat(), "note": v.note,
                          "created_by": v.created_by_name, "created_at": v.created_at.isoformat()} for v in versions],
            "modifier_names": [{"name": n, "title": MODIFIER_TITLES[n]} for n in MODIFIER_NAMES]}


class SettingsIn(BaseModel):
    valid_from: dt.date
    payload: dict
    note: str = ""


@router.put("")
def put_settings(data: SettingsIn, principal: Principal = Depends(require_perm("settings.edit")),
                 db: Session = Depends(get_db)):
    if data.valid_from.day != 1:
        raise HTTPException(status_code=422, detail="Шаг расчёта и справочники меняются только с начала периода (1-е число)")
    try:
        validate_settings(from_payload(data.payload, "draft"))
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=domain_error_text(exc))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Некорректный формат настроек: {exc}")
    v = EngineSettingsVersion(valid_from=data.valid_from, payload_json=json.dumps(data.payload, ensure_ascii=False),
                              note=data.note[:255], created_by_name=principal.name)
    db.add(v)
    db.flush()
    audit(db, principal, "engine_settings", f"settings:{v.id}", {"valid_from": data.valid_from, "note": data.note})
    db.commit()
    return {"ok": True, "id": v.id}


@router.get("/modifiers")
def list_modifiers(year: int, month: int, principal: Principal = Depends(require_perm("settings.view")),
                   db: Session = Depends(get_db)):
    first = dt.date(year, month, 1)
    last = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    rows = db.scalars(select(DayModifier).where(
        ((DayModifier.date >= first) & (DayModifier.date <= last)) | (DayModifier.period_start == first))
        .order_by(DayModifier.date, DayModifier.id))
    return [{"id": m.id, "name": m.name, "title": MODIFIER_TITLES.get(m.name, m.name), "value": m.value,
             "employee_id": m.employee_id, "group": m.group, "date": m.date.isoformat() if m.date else None,
             "period_start": m.period_start.isoformat() if m.period_start else None, "note": m.note,
             "created_by": m.created_by_name} for m in rows]


class ModifierIn(BaseModel):
    name: str
    value: str                       # "1" | "0" | "auto"
    employee_id: Optional[int] = None
    group: str = ""
    date: Optional[dt.date] = None
    period_start: Optional[dt.date] = None
    note: str = ""


@router.post("/modifiers")
def add_modifier(data: ModifierIn, principal: Principal = Depends(require_perm("settings.edit")),
                 db: Session = Depends(get_db)):
    if data.name not in MODIFIER_NAMES:
        raise HTTPException(status_code=422, detail="Неизвестный модификатор")
    if data.value not in ("1", "0", "auto") or (data.value == "auto" and data.name != "plan_equals_fact"):
        raise HTTPException(status_code=422, detail="Значение: 1 / 0 (для «План=Факт» ещё auto)")
    if bool(data.date) == bool(data.period_start):
        raise HTTPException(status_code=422, detail="Укажите либо день, либо период (1-е число месяца)")
    if data.employee_id and data.group:
        raise HTTPException(status_code=422, detail="Область — сотрудник ИЛИ группа")
    m = DayModifier(**{**data.model_dump(), "created_by_name": principal.name})
    db.add(m)
    db.flush()
    audit(db, principal, "day_modifier_create", f"modifier:{m.id}", data.model_dump())
    db.commit()
    return {"id": m.id}


@router.delete("/modifiers/{mod_id}")
def delete_modifier(mod_id: int, principal: Principal = Depends(require_perm("settings.edit")),
                    db: Session = Depends(get_db)):
    m = db.get(DayModifier, mod_id)
    if not m:
        raise HTTPException(status_code=404, detail="Модификатор не найден")
    audit(db, principal, "day_modifier_delete", f"modifier:{m.id}", {"name": m.name, "date": m.date})
    db.delete(m)
    db.commit()
    return {"ok": True}
