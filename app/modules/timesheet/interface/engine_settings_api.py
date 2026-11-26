"""API настроек расчёта: версии справочников, модификаторы дня, «Обзор» и «Проверитель».

Правила — в ``application/engine_settings.py``; роутер разбирает запрос и проверяет право.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.core.schemas import Ok

from ..application import engine_settings
from ..application.engine_settings import ModifierIn, SettingsIn
from .schemas import (
    EngineSettingsOut,
    HealthOut,
    ModifierAddedOut,
    ModifierOut,
    ResolvedRulesOut,
    SettingsPublishedOut,
)

router = APIRouter(prefix="/api/engine-settings", tags=["engine-settings"])


@router.get("", response_model=EngineSettingsOut)
def get_settings(on: Optional[dt.date] = None, version_id: Optional[int] = None,
                 principal: Principal = Depends(require_perm("settings.view")), db: Session = Depends(get_db)):
    """Справочники на дату или конкретная публикация и история."""
    return engine_settings.current(db, on, version_id=version_id)


@router.put("", response_model=SettingsPublishedOut)
def put_settings(data: SettingsIn, principal: Principal = Depends(require_perm("settings.edit")),
                 db: Session = Depends(get_db)):
    """Опубликовать новую версию справочников."""
    return engine_settings.publish(db, principal, data)


@router.get("/modifiers", response_model=list[ModifierOut])
def list_modifiers(year: int, month: int, principal: Principal = Depends(require_perm("settings.view")),
                   db: Session = Depends(get_db)):
    return engine_settings.list_modifiers(db, year, month)


@router.post("/modifiers", response_model=ModifierAddedOut)
def add_modifier(data: ModifierIn, principal: Principal = Depends(require_perm("settings.edit")),
                 db: Session = Depends(get_db)):
    return {"id": engine_settings.add_modifier(db, principal, data)}


@router.delete("/modifiers/{mod_id}", response_model=Ok)
def delete_modifier(mod_id: int, principal: Principal = Depends(require_perm("settings.edit")),
                    db: Session = Depends(get_db)):
    engine_settings.delete_modifier(db, principal, mod_id)
    return Ok()


@router.get("/health", response_model=HealthOut)
def get_health(on: Optional[dt.date] = None, principal: Principal = Depends(require_perm("settings.view")),
               db: Session = Depends(get_db)):
    """Здоровье настроек и паспорт объекта для экрана «Обзор»."""
    return engine_settings.health(db, on)


@router.get("/rules/resolve", response_model=ResolvedRulesOut)
def resolve_rules(employee_id: int, date: dt.date, name: Optional[str] = None,
                  principal: Principal = Depends(require_perm("settings.view")),
                  db: Session = Depends(get_db)):
    """«Проверитель»: какое значение правила подействовало для сотрудника в день и почему."""
    return engine_settings.resolve_rules(db, employee_id, date, name)
