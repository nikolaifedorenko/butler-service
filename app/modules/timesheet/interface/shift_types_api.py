"""Словарь «Смены и отсутствия» и значения Табеля: справочник Графика с ревизиями."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal, current_principal
from app.core.db import get_db
from app.core.format import normalize_hex_color
from app.core.permissions import require_perm
from app.core.time import local_date

from ..application.catalog import ShiftType
from ..application.engine_common import (
    day_code_rows,
)
from ..application.shiftrev import REV_FIELDS, add_revision, archive_shift, freeze_before_update
from .dates import parse_date

router = APIRouter(prefix="/api", tags=["directory"])


# ──────────────────────────────── смены (словарь) ────────────────────────────────
def _shift_dict(s: ShiftType, revisions: int = 0) -> dict:
    return {
        "id": s.id, "code": s.code, "name": s.name,
        "kind": s.kind, "start_time": s.start_time, "end_time": s.end_time,
        "overnight": s.overnight, "color": s.color,
        "sort_order": s.sort_order, "is_working": s.is_working,
        "counts_as_worked": s.counts_as_worked, "is_default_off": s.is_default_off,
        "planned_hours": s.planned_hours, "active": s.active,
        "doc_type": s.doc_type or "",
        "punch_in_allowed": bool(s.punch_in_allowed), "punch_out_allowed": bool(s.punch_out_allowed),
        "archived": bool(s.archived_at) or not s.active,
        "archived_at": s.archived_at.isoformat() if s.archived_at else None,
        "revisions": revisions,
    }


@router.get("/tabel-values")
def tabel_values(principal: Principal = Depends(current_principal),
                 db: Session = Depends(get_db)):
    """Значения рабочего дня для выбора в карточке сотрудника и диалогах перевода
    (18.10.2026): строки CFG-WINDOWS кодов, несущих часы, — код, часы и окно."""
    from ..application.catalog import SqlSettingsAdapter
    from ..application.engine_common import day_code_rows
    from ..application.months import month_period

    _today = local_date()
    st = SqlSettingsAdapter(db).load(month_period(_today.year, _today.month))
    rows = day_code_rows(db)
    out = []
    for key, w in sorted(st.windows.items(), key=lambda kv: (kv[0].split(" ")[0], w_start(kv[1]))):
        code, _, hours = key.partition(" ")
        row = rows.get(code) or {}
        if not row.get("carries_hours"):
            continue
        out.append({"value": key, "code": code, "hours": hours,
                    "title": row.get("title") or code,
                    "start_hm": f"{w.start_minute // 60:02d}:{w.start_minute % 60:02d}",
                    "end_hm": f"{w.end_minute // 60:02d}:{w.end_minute % 60:02d}"})
    return {"values": out}


def w_start(w) -> int:
    return w.start_minute


@router.get("/shift-types")
def list_shift_types(include_archived: bool = False,
                     principal: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Словарь смен. Архивные (удалённые) скрыты: в прошлом они продолжают считаться,
    но в новых ячейках недоступны. include_archived=true — показать и их.
    Чтение — любому вошедшему (нужно батлерам для легенды графика), правки — менеджерам."""
    from ..application.catalog import ShiftRevision

    stmt = select(ShiftType).order_by(ShiftType.sort_order, ShiftType.id)
    if not include_archived:
        stmt = stmt.where(ShiftType.active.is_(True))
    types = db.scalars(stmt).all()
    counts: dict[int, int] = {}
    for rev in db.scalars(select(ShiftRevision).where(
            ShiftRevision.shift_type_id.in_([t.id for t in types]) if types else
            ShiftRevision.shift_type_id < 0)):
        counts[rev.shift_type_id] = counts.get(rev.shift_type_id, 0) + 1
    return [_shift_dict(t, counts.get(t.id, 0)) for t in types]


@router.get("/shift-types/tabel-codes")
def shift_tabel_codes(principal: Principal = Depends(current_principal),
                      db: Session = Depends(get_db)):
    """Словарь кодов Табеля для редактора смены (T1).

    Поле «код в табеле» — выбор из существующих кодов CFG-DAY-CODES, а не свободный
    текст: именно код определяет стандартное окно дня и значение Табеля при
    автозаполнении из циклов. Чтение — любому вошедшему (как у списка смен):
    справочник нужен и легенде, и редактору.
    """
    return {"codes": list(day_code_rows(db).values())}


class ShiftTypeIn(BaseModel):
    code: str
    name: str
    kind: str = "work"
    start_time: str = ""
    end_time: str = ""
    overnight: bool = False
    color: str = "#6b7280"
    sort_order: int = 100
    is_working: bool = True
    counts_as_worked: bool = True
    is_default_off: bool = False
    doc_type: str = ""              # какой документ печатаем по этому отсутствию
    punch_in_allowed: bool = True   # можно ли жать «Пришёл» во время этой смены/отсутствия
    punch_out_allowed: bool = True  # можно ли жать «Ушёл»
    effective_from: Optional[str] = None  # изменения вступают в силу с даты; прошлое не меняется

    @field_validator("color", mode="before")
    @classmethod
    def _valid_color(cls, v):
        return normalize_hex_color(v, "#6b7280")


@router.post("/shift-types")
def create_shift_type(payload: ShiftTypeIn, principal: Principal = Depends(require_perm("settings.edit")),
                      db: Session = Depends(get_db)):
    if db.scalar(select(ShiftType).where(ShiftType.code == payload.code)):
        raise HTTPException(status_code=409, detail="Такой код смены уже существует")
    data = payload.model_dump()
    data.pop("effective_from", None)
    st = ShiftType(**data)
    db.add(st)
    audit(db, principal, "shift_type_create", payload.code, payload.model_dump())
    db.commit()
    return _shift_dict(st)


@router.put("/shift-types/{type_id}")
def update_shift_type(type_id: int, payload: ShiftTypeIn,
                      principal: Principal = Depends(require_perm("settings.edit")), db: Session = Depends(get_db)):
    """Правка смены НЕ ломает прошлое: старые значения фиксируются ревизией,
    новые действуют с `effective_from` (по умолчанию — с сегодняшнего дня).
    Отработанные смены в прошлых месяцах считаются по прежним часам."""
    from ..application.catalog import ShiftRevision

    st = db.get(ShiftType, type_id)
    if not st:
        raise HTTPException(status_code=404, detail="Тип смены не найден")
    data = payload.model_dump()
    eff_raw = data.pop("effective_from", None)
    eff = parse_date(eff_raw) or local_date()

    new_code = data.get("code") or st.code
    if new_code != st.code and db.scalar(select(ShiftType).where(
            ShiftType.code == new_code, ShiftType.id != st.id)):
        raise HTTPException(status_code=409, detail="Такой код смены уже существует")
    if st.is_default_off and not data.get("is_default_off", True):
        other = db.scalar(select(ShiftType).where(ShiftType.is_default_off.is_(True),
                                                  ShiftType.id != st.id))
        if other is None:
            raise HTTPException(status_code=409,
                                detail="Это единственная смена «выходной по умолчанию»: "
                                       "сначала отметьте признаком другую смену")

    changes = {f: (getattr(st, f), data[f]) for f in REV_FIELDS
               if f in data and getattr(st, f) != data[f]}
    if changes:
        # снимок прежних значений — они продолжат действовать для дат до `eff`
        freeze_before_update(db, st, eff)
        for k, v in data.items():
            setattr(st, k, v)
        add_revision(db, st, eff)
        audit(db, principal, "shift_type_update", st.code,
              {"changes": {k: [str(a), str(b)] for k, (a, b) in changes.items()},
               "effective_from": eff.isoformat()})
        db.flush()   # график читается по ревизиям; УТ движок v4 считает при чтении
    else:
        for k, v in data.items():
            setattr(st, k, v)
        audit(db, principal, "shift_type_update", st.code, payload.model_dump())
    db.commit()
    revisions = db.scalar(select(func.count(ShiftRevision.id)).where(
        ShiftRevision.shift_type_id == st.id)) or 0
    return _shift_dict(st, revisions)


@router.delete("/shift-types/{type_id}")
def delete_shift_type(type_id: int, principal: Principal = Depends(require_perm("settings.edit")),
                      db: Session = Depends(get_db)):
    """«Удаление» смены из словаря = АРХИВАЦИЯ: прошлые графики и табели продолжают
    считаться по ней, но в новых ячейках она недоступна."""
    st = db.get(ShiftType, type_id)
    if not st:
        raise HTTPException(status_code=404, detail="Тип смены не найден")
    if st.archived_at or not st.active:
        raise HTTPException(status_code=409, detail="Смена уже в архиве")
    if st.is_default_off:
        raise HTTPException(status_code=409,
                            detail="Нельзя архивировать смену «выходной по умолчанию»: "
                                   "её использует базовый цикл. Сначала назначьте признак другой смене.")
    archive_shift(db, st)
    audit(db, principal, "shift_type_archive", st.code,
          {"note": "прошлые ячейки продолжают считаться по этой смене"})
    db.commit()
    return {"ok": True, "archived": True, "shift": _shift_dict(st)}


@router.post("/shift-types/{type_id}/restore")
def restore_shift_type(type_id: int, principal: Principal = Depends(require_perm("settings.edit")),
                       db: Session = Depends(get_db)):
    """Вернуть смену из архива в словарь."""
    st = db.get(ShiftType, type_id)
    if not st:
        raise HTTPException(status_code=404, detail="Тип смены не найден")
    st.active = True
    st.archived_at = None
    audit(db, principal, "shift_type_restore", st.code)
    db.commit()
    return {"ok": True, "shift": _shift_dict(st)}


@router.get("/shift-types/{type_id}/revisions")
def shift_revisions(type_id: int, principal: Principal = Depends(require_perm("settings.view")),
                    db: Session = Depends(get_db)):
    """История значений смены: какие часы действовали в прошлом."""
    from ..application.catalog import ShiftRevision

    st = db.get(ShiftType, type_id)
    if not st:
        raise HTTPException(status_code=404, detail="Тип смены не найден")
    revs = db.scalars(select(ShiftRevision).where(
        ShiftRevision.shift_type_id == type_id).order_by(ShiftRevision.valid_from)).all()
    return {"current": _shift_dict(st),
            "revisions": [{"valid_from": r.valid_from.isoformat(),
                           **{f: getattr(r, f) for f in REV_FIELDS}} for r in revs]}
