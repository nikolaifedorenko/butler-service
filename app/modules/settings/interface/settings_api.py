"""API экрана «Настройки»: прочие правила объекта. Правила — в ``application/rules.py``;
правила расчёта часов по версиям — /api/engine-settings."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..application import rules
from ..application.rules import BaseIn, DocIn, RuleIn
from .schemas import BaseSavedOut, DocSavedOut, RulesSavedOut, SettingsOut

router = APIRouter(prefix="/api/settings", tags=["settings"])
EDIT = require_perm("settings.edit")


@router.get("", response_model=SettingsOut)
def get_settings_api(principal: Principal = Depends(require_perm("settings.view")), db: Session = Depends(get_db)):
    return rules.view(db)


@router.put("/doc", response_model=DocSavedOut)
def update_doc(payload: DocIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Реквизиты организации и тексты заявлений для печати документов."""
    return {"doc": rules.update_doc(db, principal, payload)}


@router.put("/base", response_model=BaseSavedOut)
def update_base(payload: BaseIn, principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Базовый цикл объекта: какие дни рабочие у каждого блока графика."""
    return {"base": rules.update_base(db, principal, payload)}


@router.put("", response_model=RulesSavedOut)
def update_settings(payload: list[RuleIn], principal: Principal = Depends(EDIT), db: Session = Depends(get_db)):
    """Сохранить правила объекта."""
    return {"rules": rules.update_rules(db, principal, payload)}
