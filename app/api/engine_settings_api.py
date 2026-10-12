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
from ..engine.domain.types.entities import Period
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
    if data.valid_from.day not in (1, 16):
        raise HTTPException(status_code=422,
                            detail="Шаг расчёта и справочники меняются только с границы периода "
                                   "(1-е или 16-е число — по гранулярности, RUL-PERIOD-GRANULARITY)")
    try:
        validate_settings(from_payload(data.payload))
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


def _scope_form(data: ModifierIn) -> tuple:
    """Форма области действия записи (CHK-MODIFIER-SCOPE): кто × день/период."""
    return (bool(data.employee_id), bool(data.group), bool(data.date), bool(data.period_start))


def _conflicting(db: Session, data: ModifierIn, period: Optional[Period],
                 granularity: str) -> Optional[DayModifier]:
    """Запись того же уровня приоритета, матчащая те же дни (CHK-MODIFIER-CONFLICT).

    Ищем до сохранения: конфликт, обнаруженный при загрузке настроек, останавливает
    расчёт всех вкладок периода, а исправить его можно только здесь. Форма области
    задаёт уровень один-в-один (3.5), поэтому сравниваем её, а не номер уровня:
    доменный `scope_level` принимает `ModifierEntry`, которого на стороне записи ещё нет.
    """
    form = _scope_form(data)
    q = select(DayModifier).where(DayModifier.name == data.name,
                                  DayModifier.employee_id == data.employee_id,
                                  DayModifier.group == (data.group or ""))
    for other in db.scalars(q):
        if (bool(other.employee_id), bool(other.group), bool(other.date),
                bool(other.period_start)) != form:
            continue
        if data.date is not None:
            if other.date == data.date:
                return other
            continue
        if period is None or other.period_start is None:
            continue
        other_end = _period_end_of(other.period_start, granularity)
        if max(other.period_start, period.start) <= min(other_end, period.end):
            return other
    return None


def _granularity(db: Session, on: dt.date) -> str:
    ver = base_version(db, on)
    if ver is None:
        return "month"
    try:
        return json.loads(ver.payload_json).get("period_granularity", "month")
    except (ValueError, TypeError):
        return "month"


def _period_end_of(start: dt.date, granularity: str) -> dt.date:
    """Конец периода записи: месяц либо половина месяца по гранулярности (R36)."""
    nxt = dt.date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    month_end = nxt - dt.timedelta(days=1)
    if start.day == 16:
        return month_end
    if start.day == 1 and granularity != "month":
        return dt.date(start.year, start.month, 15)
    return month_end


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
    granularity = _granularity(db, data.period_start or data.date or dt.date.today())
    period = None if data.date else Period(data.period_start,
                                           _period_end_of(data.period_start, granularity))
    conflict = _conflicting(db, data, period, granularity)
    if conflict is not None:
        scope = (f"сотрудник #{conflict.employee_id}" if conflict.employee_id
                 else f"группа «{conflict.group}»" if conflict.group else "все сотрудники")
        when = (f"{conflict.date:%d.%m.%Y}" if conflict.date else
                f"период с {conflict.period_start:%d.%m.%Y}")
        raise HTTPException(status_code=409, detail={
            "message": (f"Конфликт правил: «{MODIFIER_TITLES.get(data.name, data.name)}» уже задано "
                        f"для области «{scope}», {when} (запись #{conflict.id}"
                        + (f", автор {conflict.created_by_name}" if conflict.created_by_name else "")
                        + "). Два правила одного уровня на один день останавливают расчёт "
                          "(CHK-MODIFIER-CONFLICT) — удалите прежнее или сузьте область."),
            "conflict_with": {"id": conflict.id, "name": conflict.name, "value": conflict.value,
                              "employee_id": conflict.employee_id, "group": conflict.group or None,
                              "date": conflict.date.isoformat() if conflict.date else None,
                              "period_start": conflict.period_start.isoformat()
                              if conflict.period_start else None,
                              "author": conflict.created_by_name or ""}})
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
