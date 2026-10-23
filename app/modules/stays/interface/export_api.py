"""Выгрузка «Шахматки» в Excel (§8): обезличенная — stays.occupancy или stays.view;
полная — stays.export и stays.guests. Каждая выгрузка — в журнале аудита."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import principal_permissions, require_perm

from ..application.export import export_xlsx
from ..application.views import ViewError

router = APIRouter(prefix="/api/stays", tags=["stays"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/export")
def export(first: dt.date, last: dt.date, kind: Literal["full", "anon"] = "anon",
           principal: Principal = Depends(require_perm("stays.occupancy", "stays.view", "stays.export")),
           db: Session = Depends(get_db)):
    perms = principal_permissions(db, principal)
    if kind == "full" and not {"stays.export", "stays.guests"} <= perms:
        raise HTTPException(status_code=403, detail="Полная выгрузка — с правами «Выгрузка» и «Профили гостей»")
    if kind == "anon" and not {"stays.occupancy", "stays.view"} & perms:
        raise HTTPException(status_code=403, detail="Недостаточно прав для выгрузки")
    try:
        content = export_xlsx(db, first, last, kind)
    except ViewError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    audit(db, principal, "stays_export", f"export:{kind}", {"kind": kind, "first": first.isoformat(),
                                                            "last": last.isoformat()})
    db.commit()
    name = f"shakhmatka_{kind}_{first.isoformat()}_{last.isoformat()}.xlsx"
    return Response(content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})
