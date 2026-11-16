"""Начальная загрузка фонда («заменить всё»), копии и переключатель «в эксплуатации» (§9.3).

Операции правом ``stays.reset``. Ошибки файла — ``FundFileError`` (422 со списком ошибок),
и тогда ничего не удалено.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transactional
from app.core.errors import NotFound

from . import fund_drafts as fd
from . import fund_reset as fr
from . import fund_xlsx as fx
from .previewed import discarded


def reset_preview(db: Session, data: bytes) -> dict:
    """Что будет удалено и загружено, предупреждения и отпечаток данных; ничего не меняет."""
    parsed, errors = fx.parse_fund(data)
    if parsed is None:
        raise fd.FundFileError(errors)
    return discarded(db, lambda: fr.preview(db, parsed))


@transactional
def reset(db: Session, principal: Principal, data: bytes, filename: str | None, confirm: str,
          fingerprint: str) -> dict:
    """Замена: нужны ``confirm`` = «ЗАМЕНИТЬ» (иначе 422) и отпечаток предпросмотра (данные
    изменились — 409). Пока «в эксплуатации» — 409. Ответ — имя копии и адрес её скачивания."""
    parsed, errors = fx.parse_fund(data)
    if parsed is None:
        raise fd.FundFileError(errors)
    out = fr.initial_load(db, parsed, principal, fr.parse_fingerprint(fingerprint),
                          confirm=confirm, filename=filename or "")
    return {**out, "backup_url": f"/api/stays/fund/backups/{out['backup']}"}


@transactional
def backup_file(db: Session, principal: Principal, name: str) -> Path:
    """Копия перед начальной загрузкой: имя строго stays-YYYYMMDD-HHMMSS.xlsx, без путей. В
    копии персональные данные гостей — скачивание попадает в журнал аудита."""
    path = fr.backup_path(name)
    if path is None:
        raise NotFound("Копии нет")
    audit(db, principal, "stays_reset", f"backup:{name}", {"download": True})
    return path


@transactional
def set_in_production(db: Session, principal: Principal, value: bool) -> dict:
    """Переключатель «Шахматка в эксплуатации»: включён — начальной загрузки нет."""
    return {"in_production": fr.set_in_production(db, principal, value)}
