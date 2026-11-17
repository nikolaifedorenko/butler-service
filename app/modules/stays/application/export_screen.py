"""Выгрузка шахматки в Excel (§8): обезличенная — ``stays.occupancy`` или ``stays.view``; полная —
``stays.export`` и ``stays.guests``. Каждая выгрузка — в журнале аудита."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transactional
from app.core.errors import Forbidden
from app.core.permissions import principal_permissions

from .export import export_xlsx


@transactional
def export(db: Session, principal: Principal, first: dt.date, last: dt.date,
           kind: Literal["full", "anon"]) -> tuple[bytes, str]:
    """Содержимое файла и его имя."""
    perms = principal_permissions(db, principal)
    if kind == "full" and not {"stays.export", "stays.guests"} <= perms:
        raise Forbidden("Полная выгрузка — с правами «Выгрузка» и «Профили гостей»")
    if kind == "anon" and not {"stays.occupancy", "stays.view"} & perms:
        raise Forbidden("Недостаточно прав для выгрузки")
    content = export_xlsx(db, first, last, kind)
    audit(db, principal, "stays_export", f"export:{kind}", {"kind": kind, "first": first.isoformat(),
                                                            "last": last.isoformat()})
    return content, f"shakhmatka_{kind}_{first.isoformat()}_{last.isoformat()}.xlsx"
