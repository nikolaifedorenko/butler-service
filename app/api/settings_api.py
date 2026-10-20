"""Прочие правила объекта + служебные эндпоинты. Правила расчёта часов — /api/engine-settings."""
from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import Principal, audit
from ..base_schedule import DEFAULT_BASE, load_base_config, save_base_config
from ..db import get_db
from ..deps import local_date
from ..doc_templates import load_doc_templates, save_doc_templates
from ..models import (
    Employee,
    EngineSettingsVersion,
    PeriodClosing,
    Punch,
    ScheduleShift,
    Setting,
    TabelDay,
    User,
)
from ..permissions import require_perm
from ..schedule_helpers import DEFAULT_RULES, load_rules, rule_options

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Глобальные подстраховки модификаторов (уровень 7, CFG-MODIFIERS) и лимиты: читаются
# из действующей версии справочников, чтобы интерфейс показывал «Оплачиваются ли
# переработки» и соседние правила словами, а не только ключами в JSON.
DEFAULT_TITLES = {
    "pays_overtime": "Оплачиваются ли переработки",
    "double_overtime": "Двойные переработки",
    "plan_equals_fact": "План=Факт",
}
DEFAULT_HINTS = {
    "pays_overtime": "«Нет» — переработка дня уходит в банк часов по весу кода и не попадает в УТ",
    "double_overtime": "«Да» — вес часа переработки 2 (коды ДЯ2/ДН2). Дни производственного "
                       "календаря и ВИП-периоды подмешиваются автоматически",
    "plan_equals_fact": "«Авто» разрешается в «Да» только колонкой кода Табеля (стартово у «К»). "
                        "День без отметок и без факта считается отработанным как запланировано",
}


def defaults_of(db: Session, on: dt.date) -> dict:
    """Глобальные значения модификаторов и лимиты из версии, действующей на дату `on`."""
    from ..engine.adapters.sql_settings import base_version

    ver = base_version(db, on)
    payload = json.loads(ver.payload_json) if ver else {}
    gd = payload.get("global_defaults") or {}
    return {
        "version": {"id": ver.id if ver else None,
                    "valid_from": ver.valid_from.isoformat() if ver else None,
                    "note": ver.note if ver else "", "on": on.isoformat()},
        "modifiers": [{"name": name, "title": DEFAULT_TITLES[name], "hint": DEFAULT_HINTS[name],
                       "value": gd.get(name)} for name in DEFAULT_TITLES],
        "limits": {"step_minutes": payload.get("step_minutes"),
                   "late_limit_minutes": payload.get("late_limit_minutes"),
                   "period_granularity": payload.get("period_granularity")},
    }


@router.get("")
def get_settings_api(principal: Principal = Depends(require_perm("settings.view")), db: Session = Depends(get_db)):
    rules = load_rules(db)
    meta = {o["key"]: o for o in rule_options()}
    items = [{"key": k, "value": rules[k], "default": DEFAULT_RULES[k],
              "description": meta[k]["description"], "type": meta[k]["type"]} for k in DEFAULT_RULES]
    # Правила показываются по версии, действующей СЕГОДНЯ: период закрывают по состоянию
    # на сейчас, а версия, вступающая позже, отмечена отдельно (upcoming_versions) —
    # иначе администратор видит завтрашние значения и принимает их за текущие.
    today = local_date()
    defaults = defaults_of(db, today)
    defaults["upcoming_versions"] = [
        {"id": v.id, "valid_from": v.valid_from.isoformat(), "note": v.note or ""}
        for v in db.scalars(select(EngineSettingsVersion)
                            .where(EngineSettingsVersion.valid_from > today)
                            .order_by(EngineSettingsVersion.valid_from, EngineSettingsVersion.id))]
    counts = {
        "employees": db.scalar(select(func.count(Employee.id)).where(Employee.active.is_(True))) or 0,
        "users": db.scalar(select(func.count(User.id))) or 0,
        "schedule_shifts": db.scalar(select(func.count(ScheduleShift.id))) or 0,
        "punches": db.scalar(select(func.count(Punch.id))) or 0,
        "tabel_days": db.scalar(select(func.count(TabelDay.id))) or 0,
        "period_closings": db.scalar(select(func.count(PeriodClosing.id))) or 0,
    }
    return {"rules": rules, "items": items, "counts": counts,
            "base": load_base_config(db), "doc": load_doc_templates(db),
            "engine_defaults": defaults}


class DocIn(BaseModel):
    company: str = ""
    director: str = ""
    vacation: str = ""
    vacation_unpaid: str = ""
    day_off_hours: str = ""       # заявление на выходной за ранее отработанные часы
    time_off_request: str = ""    # заявление «отпросился с … до …»


@router.put("/doc")
def update_doc(payload: DocIn, principal: Principal = Depends(require_perm("settings.edit")),
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
def update_base(payload: BaseIn, principal: Principal = Depends(require_perm("settings.edit")),
                db: Session = Depends(get_db)):
    """Базовый цикл объекта: какие дни рабочие у Смены 1 / Смены 2 / Администрации — на все месяцы."""
    import datetime as _dt

    from ..base_schedule import working_flag

    try:
        _dt.date.fromisoformat(payload.anchor)
    except ValueError:
        raise HTTPException(status_code=422, detail="Опорная дата должна быть в формате ГГГГ-ММ-ДД")
    cfg = {"cycle": payload.cycle, "anchor": payload.anchor, "groups": payload.groups or DEFAULT_BASE["groups"]}
    probe = local_date()
    for name, g in cfg["groups"].items():
        try:
            working_flag(cfg, g, probe)
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
def update_settings(payload: list[RuleIn], principal: Principal = Depends(require_perm("settings.edit")),
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
