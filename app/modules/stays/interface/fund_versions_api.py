"""API версий фонда (спецификация stays-fund-versions §4, §6): снимок на дату и черновик.

Чтение — тем, кто видит шахматку (READ), запись — правом stays.setup. Каждая запись черновика
несёт rev (оптимистичная блокировка: 409 при расхождении) и возвращает новый rev. Начальная
загрузка («заменить всё») и переключатель «в эксплуатации» — правом stays.reset (§9.3).

Правила — в прикладном слое: ``fund_screen`` (чтение), ``fund_draft_edit`` (черновик, публикация,
загрузка файла), ``fund_dictionaries`` (флаги и виды), ``fund_admin`` (начальная загрузка).
Роутер разбирает запрос и проверяет право.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.permissions import require_perm

from ..application import fund_admin, fund_dictionaries, fund_draft_edit, fund_screen
from ..application.fund_forms import (
    ArchiveIn,
    DraftCategoryIn,
    DraftGroupIn,
    DraftIn,
    DraftMoveIn,
    DraftUnitIn,
    FlagIn,
    FlagValueIn,
    InProductionIn,
    KindIn,
    MergeIn,
    PublishIn,
    SplitIn,
)
from ._upload import read_upload
from .fund_api import READ, SETUP
from .schemas import (
    DeleteVersionOut,
    DraftEntityOut,
    DraftMovedOut,
    DraftOpenedOut,
    DraftRevOut,
    DraftSplitOut,
    FundDiffOut,
    FundImportOut,
    FundSnapshotOut,
    FundVersionRowOut,
    IdOut,
    InProductionOut,
    PublishOut,
    ResetOut,
    ResetPreviewOut,
)

router = APIRouter(prefix="/api/stays", tags=["stays"])
RESET = require_perm("stays.reset")
PREVIEW = Query(False, alias="preview", description="Только показать, что изменится, без сохранения")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# ── чтение ───────────────────────────────────────────────────────────────────


@router.get("/fund/snapshot", response_model=FundSnapshotOut)
def get_snapshot(date: Optional[dt.date] = None, version_id: Optional[int] = None,
                 principal: Principal = Depends(READ), db: Session = Depends(get_db)):
    return fund_screen.snapshot(db, date, version_id)


@router.get("/fund/versions", response_model=list[FundVersionRowOut])
def list_versions(principal: Principal = Depends(READ), db: Session = Depends(get_db)):
    return fund_screen.versions(db)


@router.get("/fund/draft/diff", response_model=FundDiffOut)
def draft_diff(principal: Principal = Depends(READ), db: Session = Depends(get_db)):
    return fund_screen.draft_diff(db)


# ── запись черновика ─────────────────────────────────────────────────────────


@router.post("/fund/draft", response_model=DraftOpenedOut)
def open_draft(payload: DraftIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return fund_draft_edit.open_draft(db, principal, payload)


@router.patch("/fund/draft", response_model=DraftMovedOut)
def move_draft(payload: DraftMoveIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return fund_draft_edit.move_draft(db, principal, payload)


@router.delete("/fund/versions/{vid}", response_model=DeleteVersionOut)
def remove_version(vid: int, preview_flag: bool = PREVIEW, principal: Principal = Depends(SETUP),
                   db: Session = Depends(get_db)):
    """Удаление черновика или будущей версии и его предпросмотр (?preview=1)."""
    return fund_draft_edit.delete_version(db, principal, vid, preview_only=preview_flag)


@router.post("/fund/draft/categories", response_model=DraftEntityOut)
def create_category(payload: DraftCategoryIn, principal: Principal = Depends(SETUP),
                    db: Session = Depends(get_db)):
    return fund_draft_edit.save_category(db, principal, payload, None)


@router.put("/fund/draft/categories/{cid}", response_model=DraftEntityOut)
def update_category(cid: int, payload: DraftCategoryIn, principal: Principal = Depends(SETUP),
                    db: Session = Depends(get_db)):
    return fund_draft_edit.save_category(db, principal, payload, cid)


@router.delete("/fund/draft/categories/{cid}", response_model=DraftRevOut)
def remove_category(cid: int, rev: int = Query(), principal: Principal = Depends(SETUP),
                    db: Session = Depends(get_db)):
    return fund_draft_edit.retire_category(db, principal, rev, cid)


@router.post("/fund/draft/groups", response_model=DraftEntityOut)
def create_group(payload: DraftGroupIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return fund_draft_edit.save_group(db, principal, payload, None)


@router.put("/fund/draft/groups/{gid}", response_model=DraftEntityOut)
def update_group(gid: int, payload: DraftGroupIn, principal: Principal = Depends(SETUP),
                 db: Session = Depends(get_db)):
    return fund_draft_edit.save_group(db, principal, payload, gid)


@router.delete("/fund/draft/groups/{gid}", response_model=DraftRevOut)
def remove_group(gid: int, rev: int = Query(), principal: Principal = Depends(SETUP),
                 db: Session = Depends(get_db)):
    return fund_draft_edit.retire_group(db, principal, rev, gid)


@router.post("/fund/draft/units", response_model=DraftEntityOut)
def create_unit(payload: DraftUnitIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return fund_draft_edit.save_unit(db, principal, payload, None)


@router.put("/fund/draft/units/{uid}", response_model=DraftEntityOut)
def update_unit(uid: int, payload: DraftUnitIn, principal: Principal = Depends(SETUP),
                db: Session = Depends(get_db)):
    return fund_draft_edit.save_unit(db, principal, payload, uid)


@router.delete("/fund/draft/units/{uid}", response_model=DraftRevOut)
def remove_unit(uid: int, rev: int = Query(), principal: Principal = Depends(SETUP),
                db: Session = Depends(get_db)):
    return fund_draft_edit.retire_unit(db, principal, rev, uid)


@router.post("/fund/draft/units/merge", response_model=DraftEntityOut)
def merge_units(payload: MergeIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return fund_draft_edit.merge_units(db, principal, payload)


@router.post("/fund/draft/units/{uid}/split", response_model=DraftSplitOut)
def split_unit(uid: int, payload: SplitIn, principal: Principal = Depends(SETUP),
               db: Session = Depends(get_db)):
    return fund_draft_edit.split_unit(db, principal, uid, payload)


@router.put("/fund/draft/flags", response_model=DraftRevOut)
def put_draft_flags(payload: FlagValueIn, principal: Principal = Depends(SETUP),
                    db: Session = Depends(get_db)):
    return fund_draft_edit.set_flags(db, principal, payload)


@router.post("/fund/draft/publish", response_model=PublishOut)
def publish_draft(payload: PublishIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(SETUP),
                  db: Session = Depends(get_db)):
    """Публикация и её предпросмотр (?preview=1) — одна операция: предпросмотр откатывается (§4.3)."""
    return fund_draft_edit.publish(db, principal, payload, preview_only=preview_flag)


# ── файл фонда (§9) ──────────────────────────────────────────────────────────


@router.get("/fund/export", response_class=Response, responses={200: {"content": {XLSX: {}}}})
def export_fund(date: dt.date, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    """Фонд на дату файлом Excel — он же образец для загрузки (§9.1)."""
    data, filename = fund_screen.export_file(db, date)
    return Response(content=data, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/fund/import", response_model=FundImportOut)
def import_fund(valid_from: dt.date = Form(...), file: UploadFile = File(...),
                principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    """«Загрузить как черновик с даты» (§9.3). Ошибки файла — 422 {errors: [{sheet, row, message}]},
    и тогда не остаётся ничего, даже черновика."""
    return fund_draft_edit.import_file(db, principal, valid_from, file.filename, read_upload(file))


@router.post("/fund/reset", response_model=ResetPreviewOut | ResetOut)
def reset_fund(file: UploadFile = File(...), confirm: str = Form(""), fingerprint: str = Form(""),
               preview_flag: bool = PREVIEW, principal: Principal = Depends(RESET),
               db: Session = Depends(get_db)):
    """«Начальная загрузка (заменить всё)». ?preview=1 — что будет удалено и загружено,
    предупреждения и fingerprint; без него — замена: нужны confirm = «ЗАМЕНИТЬ» (иначе 422) и
    fingerprint предпросмотра (данные изменились — 409). Пока «в эксплуатации» — 409."""
    data = read_upload(file)
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


@router.post("/fund/flags", response_model=IdOut)
def create_flag(payload: FlagIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return fund_dictionaries.save_flag(db, principal, payload, None)


@router.put("/fund/flags/{fid}", response_model=IdOut)
def update_flag(fid: int, payload: FlagIn, principal: Principal = Depends(SETUP),
                db: Session = Depends(get_db)):
    return fund_dictionaries.save_flag(db, principal, payload, fid)


@router.put("/fund/flags/{fid}/archive", response_model=IdOut)
def archive_flag(fid: int, payload: ArchiveIn, principal: Principal = Depends(SETUP),
                 db: Session = Depends(get_db)):
    return fund_dictionaries.archive_flag(db, principal, fid, payload.archived)


@router.delete("/fund/flags/{fid}", response_model=IdOut)
def remove_flag(fid: int, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return fund_dictionaries.delete_flag(db, principal, fid)


# ── справочник видов категорий (вне черновика) ───────────────────────────────


@router.post("/fund/kinds", response_model=IdOut)
def create_kind(payload: KindIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return fund_dictionaries.save_kind(db, principal, payload, None)


@router.put("/fund/kinds/{kid}", response_model=IdOut)
def update_kind(kid: int, payload: KindIn, principal: Principal = Depends(SETUP),
                db: Session = Depends(get_db)):
    return fund_dictionaries.save_kind(db, principal, payload, kid)


@router.put("/fund/kinds/{kid}/archive", response_model=IdOut)
def archive_kind(kid: int, payload: ArchiveIn, principal: Principal = Depends(SETUP),
                 db: Session = Depends(get_db)):
    return fund_dictionaries.archive_kind(db, principal, kid, payload.archived)


@router.delete("/fund/kinds/{kid}", response_model=IdOut)
def remove_kind(kid: int, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    return fund_dictionaries.delete_kind(db, principal, kid)
