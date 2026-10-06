"""Прочие правила объекта + служебные эндпоинты. Правила расчёта часов — /api/engine-settings."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import Principal, audit, require_manager
from ..base_schedule import DEFAULT_BASE, load_base_config, save_base_config
from ..db import get_db
from ..deps import local_date
from ..doc_templates import load_doc_templates, save_doc_templates
from ..models import Employee, PeriodClosing, Punch, ScheduleEntry, Setting, TabelDay, User
from ..schedule_helpers import DEFAULT_RULES, load_rules, rule_options

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings_api(principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    rules = load_rules(db)
    meta = {o["key"]: o for o in rule_options()}
    items = [{"key": k, "value": rules[k], "default": DEFAULT_RULES[k],
              "description": meta[k]["description"], "type": meta[k]["type"]} for k in DEFAULT_RULES]
    counts = {
        "employees": db.scalar(select(func.count(Employee.id)).where(Employee.active.is_(True))) or 0,
        "users": db.scalar(select(func.count(User.id))) or 0,
        "schedule_entries": db.scalar(select(func.count(ScheduleEntry.id))) or 0,
        "punches": db.scalar(select(func.count(Punch.id))) or 0,
        "tabel_days": db.scalar(select(func.count(TabelDay.id))) or 0,
        "period_closings": db.scalar(select(func.count(PeriodClosing.id))) or 0,
    }
    return {"rules": rules, "items": items, "counts": counts,
            "base": load_base_config(db), "doc": load_doc_templates(db)}


class DocIn(BaseModel):
    company: str = ""
    director: str = ""
    vacation: str = ""
    vacation_unpaid: str = ""
    day_off_hours: str = ""       # заявление на выходной за ранее отработанные часы
    time_off_request: str = ""    # заявление «отпросился с … до …»


@router.put("/doc")
def update_doc(payload: DocIn, principal: Principal = Depends(require_manager),
               db: Session = Depends(get_db)):
    """Шаблоны заявлений и реквизиты организации для печати документов."""
    doc = save_doc_templates(db, payload.model_dump())
    audit(db, principal, "doc_templates_update", "settings", {})
    db.commit()
    return {"ok": True, "doc": doc}


class BaseIn(BaseModel):
    cycle: str = "2/2"
    anchor: str = "2024-01-01"
    groups: dict = {}


@router.put("/base")
def update_base(payload: BaseIn, principal: Principal = Depends(require_manager),
                db: Session = Depends(get_db)):
    """Базовый цикл объекта: какие дни рабочие у Смены 1 / Смены 2 / Администрации — на все месяцы."""
    import datetime as _dt

    from ..base_schedule import _flag_for

    try:
        _dt.date.fromisoformat(payload.anchor)
    except ValueError:
        raise HTTPException(status_code=422, detail="Опорная дата должна быть в формате ГГГГ-ММ-ДД")
    cfg = {"cycle": payload.cycle, "anchor": payload.anchor, "groups": payload.groups or DEFAULT_BASE["groups"]}
    probe = local_date()
    for name, g in cfg["groups"].items():
        try:
            _flag_for(cfg, g, probe)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Блок «{name}»: {exc}")
    save_base_config(db, cfg)
    audit(db, principal, "base_cycle_update", "settings", cfg)
    db.commit()
    return {"ok": True, "base": load_base_config(db)}


class RuleIn(BaseModel):
    key: str
    value: str


@router.put("")
def update_settings(payload: list[RuleIn], principal: Principal = Depends(require_manager),
                    db: Session = Depends(get_db)):
    """Сохранить правила расчёта (доступно администратору)."""
    changed = {}
    for item in payload:
        if item.key not in DEFAULT_RULES:
            raise HTTPException(status_code=422, detail=f"Неизвестный параметр: {item.key}")
        setting = db.get(Setting, item.key)
        if setting is None:
            setting = Setting(key=item.key, value=item.value,
                              description=next((o["description"] for o in rule_options() if o["key"] == item.key), ""))
            db.add(setting)
        else:
            setting.value = item.value
        changed[item.key] = item.value
    audit(db, principal, "settings_update", "rules", changed)
    db.commit()
    return {"ok": True, "rules": load_rules(db)}
