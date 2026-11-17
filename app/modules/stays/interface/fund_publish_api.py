"""API версий фонда, которым нужны брони (спецификация stays-fund-versions §4.3, §9.3): публикация
черновика и её предпросмотр, удаление версии, начальная загрузка («заменить всё»), копии и
переключатель «в эксплуатации». Данные фонда меняет модуль fund; здесь — перевод броней, пересчёт
размещения и сброс данных шахматки. Публикация — правом stays.setup, сброс — stays.reset.

Правила — в прикладном слое: ``fund_publish`` (публикация, удаление версии) и ``fund_admin``
(начальная загрузка). Роутер разбирает запрос и проверяет право.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm
from app.core.uploads import read_upload
from app.modules.fund.application import fund_xlsx
from app.modules.fund.application.fund_forms import InProductionIn, PublishIn

from ..application import fund_admin, fund_publish
from .directories_api import SETUP
from .schemas import DeleteVersionOut, InProductionOut, PublishOut, ResetOut, ResetPreviewOut

router = APIRouter(prefix="/api/stays", tags=["stays"])
RESET = require_perm("stays.reset")
PREVIEW = Query(False, alias="preview", description="Только показать, что изменится, без сохранения")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.delete("/fund/versions/{vid}", response_model=DeleteVersionOut)
def remove_version(vid: int, preview_flag: bool = PREVIEW, principal: Principal = Depends(SETUP),
                   db: Session = Depends(get_db)):
    """Удаление черновика или будущей версии и его предпросмотр (?preview=1)."""
    return fund_publish.delete_previewed(db, principal, vid, preview_only=preview_flag)


@router.post("/fund/draft/publish", response_model=PublishOut)
def publish_draft(payload: PublishIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(SETUP),
                  db: Session = Depends(get_db)):
    """Публикация и её предпросмотр (?preview=1) — одна операция: предпросмотр откатывается (§4.3)."""
    return fund_publish.publish_previewed(db, principal, payload, preview_only=preview_flag)


# ── файл фонда (§9) ──────────────────────────────────────────────────────────


@router.post("/fund/reset", response_model=ResetPreviewOut | ResetOut)
def reset_fund(file: UploadFile = File(...), confirm: str = Form(""), fingerprint: str = Form(""),
               preview_flag: bool = PREVIEW, principal: Principal = Depends(RESET),
               db: Session = Depends(get_db)):
    """«Начальная загрузка (заменить всё)». ?preview=1 — что будет удалено и загружено,
    предупреждения и fingerprint; без него — замена: нужны confirm = «ЗАМЕНИТЬ» (иначе 422) и
    fingerprint предпросмотра (данные изменились — 409). Пока «в эксплуатации» — 409."""
    data = read_upload(file, fund_xlsx.MAX_FILE_BYTES)
    if preview_flag:
        return fund_admin.reset_preview(db, data)
    return fund_admin.reset(db, principal, data, file.filename, confirm, fingerprint)


@router.get("/fund/backups/{name}", response_class=FileResponse, responses={200: {"content": {XLSX: {}}}})
def get_backup(name: str, principal: Principal = Depends(RESET), db: Session = Depends(get_db)):
    """Копия перед начальной загрузкой; скачивание — в журнале аудита."""
    return FileResponse(fund_admin.backup_file(db, principal, name), media_type=XLSX, filename=name)


@router.put("/fund/in-production", response_model=InProductionOut)
def put_in_production(payload: InProductionIn, principal: Principal = Depends(RESET),
                      db: Session = Depends(get_db)):
    """Переключатель «Шахматка в эксплуатации»: включён — начальной загрузки нет (§9.3)."""
    return fund_admin.set_in_production(db, principal, payload.value)


# ── справочник флагов (вне черновика) ────────────────────────────────────────


