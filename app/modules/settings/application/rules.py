"""Прочие правила объекта: правила расчёта, базовый цикл графика, реквизиты для документов.
Правила расчёта часов по версиям — в модуле ``timesheet`` (справочники движка)."""
from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transactional
from app.core.errors import Validation
from app.core.identity import User
from app.core.settings_store import Setting
from app.core.time import local_date
from app.modules.docs.application.doc_templates import load_doc_templates, save_doc_templates
from app.modules.people.application import Employee
from app.modules.timesheet.application.base_schedule import (
    DEFAULT_BASE,
    load_base_config,
    save_base_config,
    working_flag,
)
from app.modules.timesheet.application.catalog import (
    EngineSettingsVersion,
    PeriodClosing,
    Punch,
    ScheduleShift,
    TabelDay,
    base_version,
)
from app.modules.timesheet.application.schedule_helpers import DEFAULT_RULES, load_rules, rule_options


class DocIn(BaseModel):
    """Реквизиты организации и тексты заявлений."""

    company: str = ""
    director: str = ""
    vacation: str = ""
    vacation_unpaid: str = ""
    day_off_hours: str = ""       # заявление на выходной за ранее отработанные часы
    time_off_request: str = ""    # заявление «отпросился с … до …»


class BaseIn(BaseModel):
    """Базовый цикл объекта: какие дни рабочие у каждого блока графика."""

    cycle: str = "2/2"
    anchor: str = "2024-01-01"
    groups: dict = {}


class RuleIn(BaseModel):
    key: str
    value: str


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
    ver = base_version(db, on)
    payload = ver.payload if ver else {}
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


def view(db: Session) -> dict:
    """Экран «Настройки»: правила, базовый цикл, реквизиты, счётчики данных и глобальные
    значения движка. Движок показан по версии, действующей сегодня; версии, которые вступят
    позже, перечислены отдельно — иначе завтрашние значения принимали бы за текущие."""
    rules = load_rules(db)
    meta = {o["key"]: o for o in rule_options()}
    items = [{"key": k, "value": rules[k], "default": DEFAULT_RULES[k],
              "description": meta[k]["description"], "type": meta[k]["type"]} for k in DEFAULT_RULES]
    today = local_date()
    defaults = defaults_of(db, today)
    defaults["upcoming_versions"] = [
        {"id": v.id, "valid_from": v.valid_from.isoformat(), "note": v.note or ""}
        for v in db.scalars(select(EngineSettingsVersion).where(EngineSettingsVersion.valid_from > today)
                            .order_by(EngineSettingsVersion.valid_from, EngineSettingsVersion.id))]
    counts = {
        "employees": db.scalar(select(func.count(Employee.id)).where(Employee.active.is_(True))) or 0,
        "users": db.scalar(select(func.count(User.id))) or 0,
        "schedule_shifts": db.scalar(select(func.count(ScheduleShift.id))) or 0,
        "punches": db.scalar(select(func.count(Punch.id))) or 0,
        "tabel_days": db.scalar(select(func.count(TabelDay.id))) or 0,
        "period_closings": db.scalar(select(func.count(PeriodClosing.id))) or 0,
    }
    return {"rules": rules, "items": items, "counts": counts, "base": load_base_config(db),
            "doc": load_doc_templates(db), "engine_defaults": defaults}


@transactional
def update_doc(db: Session, principal: Principal, data: DocIn) -> dict:
    """Сохранить реквизиты организации и тексты заявлений для печати документов."""
    doc = save_doc_templates(db, data.model_dump())
    audit(db, principal, "doc_templates_update", "settings", {})
    return doc


@transactional
def update_base(db: Session, principal: Principal, data: BaseIn) -> dict:
    """Сохранить базовый цикл объекта — он действует на все месяцы."""
    try:
        dt.date.fromisoformat(data.anchor)
    except ValueError:
        raise Validation("Опорная дата должна быть в формате ГГГГ-ММ-ДД") from None
    cfg: dict[str, Any] = {"cycle": data.cycle, "anchor": data.anchor,
                           "groups": data.groups or DEFAULT_BASE["groups"]}
    probe = local_date()
    for name, group in cfg["groups"].items():
        try:
            working_flag(cfg, group, probe)
        except ValueError as exc:
            raise Validation(f"Блок «{name}»: {exc}") from exc
    save_base_config(db, cfg)
    audit(db, principal, "base_cycle_update", "settings", cfg)
    db.flush()
    return load_base_config(db)


@transactional
def update_rules(db: Session, principal: Principal, items: list[RuleIn]) -> dict:
    """Сохранить правила; неизвестный параметр отклоняет всё сохранение."""
    changed = {}
    for item in items:
        if item.key not in DEFAULT_RULES:
            raise Validation(f"Неизвестный параметр: {item.key}")
        setting = db.get(Setting, item.key)
        if setting is None:
            db.add(Setting(key=item.key, value=item.value,
                           description=next((o["description"] for o in rule_options() if o["key"] == item.key), "")))
        else:
            setting.value = item.value
        changed[item.key] = item.value
    audit(db, principal, "settings_update", "rules", changed)
    db.flush()
    return load_rules(db)
