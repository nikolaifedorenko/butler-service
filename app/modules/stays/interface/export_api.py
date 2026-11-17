"""Выгрузка «Шахматки» в Excel (§8): обезличенная — stays.occupancy или stays.view;
полная — stays.export и stays.guests. Каждая выгрузка — в журнале аудита.

Правила — в прикладном слое: ``application/export_screen.py``.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..application import export_screen

router = APIRouter(prefix="/api/stays", tags=["stays"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/export", response_class=Response, responses={200: {"content": {XLSX: {}}}})
def export(first: dt.date, last: dt.date, kind: Literal["full", "anon"] = "anon",
           principal: Principal = Depends(require_perm("stays.occupancy", "stays.view", "stays.export")),
           db: Session = Depends(get_db)):
    content, filename = export_screen.export(db, principal, first, last, kind)
    return Response(content, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
