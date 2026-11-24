"""API версий фонда (спецификация stays-fund-versions §4, §6): снимок на дату, черновик, файл фонда,
справочники флагов и видов категорий.

Чтение — тем, кто видит шахматку (READ), запись — правом stays.setup. Каждая запись черновика
несёт rev (оптимистичная блокировка: 409 при расхождении) и возвращает новый rev. Публикация и
удаление версии, начальная загрузка — в модуле stays: они знают о бронях.

Правила — в прикладном слое: ``fund_screen`` (чтение), ``fund_draft_edit`` (черновик, загрузка
файла), ``fund_dictionaries`` (флаги и виды). Роутер разбирает запрос и проверяет право.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.auth import Principal
from app.core.db import get_db
from app.core.errors import Forbidden
from app.core.permissions import require_perm
from app.core.time import local_date
from app.core.uploads import read_upload

from ..application import fund_dictionaries, fund_draft_edit, fund_screen, fund_xlsx
from ..application.fund_forms import (
    ArchiveIn,
    DraftCategoryIn,
    DraftGroupIn,
    DraftIn,
    DraftMoveIn,
    DraftUnitIn,
    FlagIn,
    FlagValueIn,
    KindIn,
    MergeIn,
    SplitIn,
)
from .schemas import (
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
)

router = APIRouter(prefix="/api/stays", tags=["stays"])
# чтение — тем, кто видит шахматку; батлеру (stays.mine) — ради определений полей: данных гостей здесь нет
READ = require_perm("stays.view", "stays.occupancy", "stays.setup", "stays.mine")
SNAPSHOT_READ = require_perm("stays.view", "stays.occupancy", "stays.setup", "stays.mine",
                             "stays.guests", "stays.edit", "stays.mine_guest_edit")
SETUP = require_perm("stays.setup")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# ── чтение ───────────────────────────────────────────────────────────────────


@router.get("/fund/snapshot", response_model=FundSnapshotOut)
def get_snapshot(date: Optional[dt.date] = None, version_id: Optional[int] = None,
                 principal: Principal = Depends(SNAPSHOT_READ), db: Session = Depends(get_db)):
    board_read = {"stays.view", "stays.occupancy", "stays.setup", "stays.mine"}
    if not board_read.intersection(principal.gate_permissions) and (
            version_id is not None or (date is not None and date != local_date())):
        raise Forbidden("Для профиля гостя доступен только текущий фонд")
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
    return fund_draft_edit.import_file(db, principal, valid_from, file.filename, read_upload(file, fund_xlsx.MAX_FILE_BYTES))


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
