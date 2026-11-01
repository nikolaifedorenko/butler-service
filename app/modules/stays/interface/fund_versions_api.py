"""API версий фонда (спецификация stays-fund-versions §4, §6): снимок на дату и черновик.

Чтение — тем, кто видит шахматку (READ), запись — правом stays.setup. Каждая запись черновика
несёт rev (оптимистичная блокировка: 409 при расхождении) и возвращает новый rev. Начальная
загрузка («заменить всё») и переключатель «в эксплуатации» — правом stays.reset (§9.3)."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import get_db
from app.core.identity import User
from app.core.permissions import require_perm

from ..adapters.orm import FundVersion, UnitFlag, UnitLineage
from ..application import fund_drafts as fd
from ..application import fund_reset as fr
from ..application import fund_xlsx as fx
from ..application.fund import FundError
from ..application.fund_versions import FundSnapshot, fund_on, kind_dict, kinds, snapshot_of
from ._ops import PREVIEW, run
from .fund_api import READ, SETUP, SORT, CategoryIn, _err

router = APIRouter(prefix="/api/stays", tags=["stays"])
RESET = require_perm("stays.reset")


# ── тела запросов ──────────────────────────────────────────────────────────


class DraftIn(BaseModel):
    valid_from: dt.date
    note: str = Field("", max_length=500)


class DraftMoveIn(BaseModel):
    rev: int
    valid_from: dt.date


class TransferIn(BaseModel):
    reservation_id: int
    category_id: int


class PublishIn(BaseModel):
    rev: int
    propagate: bool = True                 # перенести правки в поздние версии (§4.4)
    transfers: list[TransferIn] = Field([], max_length=500)


class DraftCategoryIn(CategoryIn):
    rev: int


class DraftGroupIn(BaseModel):
    rev: int
    title: str = Field(min_length=1, max_length=120)
    parent_id: Optional[int] = None
    sort_order: int = SORT


class UnitFields(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    category_id: int
    group_id: Optional[int] = None
    floor: str = Field("", max_length=8)


class DraftUnitIn(UnitFields):
    rev: int
    flags: list[int] = []


class PartIn(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    category_id: Optional[int] = None
    group_id: Optional[int] = None
    floor: str = Field("", max_length=8)


class SplitIn(BaseModel):
    rev: int
    parts: list[PartIn] = Field(min_length=2, max_length=50)


class MergeIn(BaseModel):
    rev: int
    unit_ids: list[int] = Field(min_length=2, max_length=50)
    label: str = Field(min_length=1, max_length=40)
    category_id: Optional[int] = None
    group_id: Optional[int] = None
    floor: str = Field("", max_length=8)


class FlagValueIn(BaseModel):
    rev: int
    flag_id: int
    unit_ids: list[int] = Field(max_length=500)
    value: bool


class FlagIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    title: str = Field(min_length=1, max_length=80)
    color: str = "#3b6fd8"
    sort_order: int = SORT

    @field_validator("color")
    @classmethod
    def _hex(cls, v: str) -> str:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise ValueError("Цвет в формате #RRGGBB")
        return v


class KindIn(BaseModel):
    title: str = Field(min_length=1, max_length=40)
    sort_order: int = SORT
    expanded: bool = False


class ArchiveIn(BaseModel):
    archived: bool


# ── чтение ─────────────────────────────────────────────────────────────────


def _version_dict(v: FundVersion) -> dict:
    return {"id": v.id, "valid_from": v.valid_from.isoformat(), "status": v.status, "rev": v.rev}


def _snapshot_dict(db: Session, version: FundVersion, snap: FundSnapshot) -> dict:
    return {
        "version": _version_dict(version),
        "categories": [{"id": c.id, "code": c.code, "title": c.title, "kind_id": c.kind_id, "weight": c.weight,
                        "escorted": c.escorted, "sort_order": c.sort_order}
                       for c in sorted(snap.categories.values(), key=lambda c: (c.sort_order, c.id))],
        "groups": [{"id": g.id, "parent_id": g.parent_id, "title": g.title, "sort_order": g.sort_order,
                    "path": list(g.path)}
                   for g in sorted(snap.groups.values(), key=lambda g: (g.sort_order, g.id))],
        "units": [{"id": u.id, "label": u.label, "category_id": u.category_id, "group_id": u.group_id,
                   "floor": u.floor, "flags": sorted(u.flags),
                   "path": list(snap.groups[u.group_id].path) if u.group_id in snap.groups else []}
                  for u in sorted(snap.units.values(), key=lambda u: (u.label, u.id))],
        "flags": [{"id": f.id, "title": f.title, "color": f.color, "sort_order": f.sort_order,
                   "archived": f.archived}
                  for f in db.scalars(select(UnitFlag).order_by(UnitFlag.sort_order, UnitFlag.id))],
        "kinds": [kind_dict(k) for k in kinds(db)],
    }


def _fund_on(db: Session, date: dt.date) -> FundSnapshot:
    try:
        return fund_on(db, date)
    except LookupError as e:
        raise HTTPException(422, str(e)) from e      # дата раньше первой версии — ошибка ввода


@router.get("/fund/snapshot")
def get_snapshot(date: Optional[dt.date] = None, version_id: Optional[int] = None,
                 principal: Principal = Depends(READ), db: Session = Depends(get_db)):
    if (date is None) == (version_id is None):
        raise HTTPException(422, "Укажите ровно один параметр: date или version_id")
    if version_id is not None:
        version = db.get(FundVersion, version_id)
        if version is None:
            raise HTTPException(404, "Версии фонда нет")
        snap = snapshot_of(db, version_id)
    else:
        snap = _fund_on(db, date)
        version = db.get(FundVersion, snap.version_id)
    return _snapshot_dict(db, version, snap)


@router.get("/fund/versions")
def list_versions(principal: Principal = Depends(READ), db: Session = Depends(get_db)):
    rows = db.execute(select(FundVersion, User.username)
                      .outerjoin(User, User.id == FundVersion.author_id)
                      .order_by(FundVersion.valid_from, FundVersion.id)).all()
    return [{"id": v.id, "valid_from": v.valid_from.isoformat(), "status": v.status, "author": name,
             "note": v.note, "published_at": v.published_at.isoformat() if v.published_at else None}
            for v, name in rows]


@router.get("/fund/draft/diff")
def draft_diff(principal: Principal = Depends(READ), db: Session = Depends(get_db)):
    draft = fd.current_draft(db)
    if draft is None:
        raise HTTPException(409, "Черновика фонда нет")
    if draft.base_version_id is None:
        return asdict(fd.FundDiff())
    out = asdict(fd.diff(db, draft.base_version_id, draft.id))
    # «новый · из 12134» (§10): у нового объекта — обозначения тех, из кого он получился
    # (деление, объединение в этом черновике); выведенный предшественник — по базе черновика
    preds: dict[int, list[int]] = {}
    for unit_id, pred in db.execute(select(UnitLineage.unit_id, UnitLineage.predecessor_id)
                                    .where(UnitLineage.version_id == draft.id)):
        preds.setdefault(unit_id, []).append(pred)
    if preds:
        mine, base = snapshot_of(db, draft.id).units, snapshot_of(db, draft.base_version_id).units
        name = {i: u.label for i, u in {**base, **mine}.items()}
        for e in out["units"]:
            if e["kind"] == "added":
                e["from"] = [name.get(p, f"#{p}") for p in sorted(preds.get(e["id"], []))]
    return out


# ── запись черновика ───────────────────────────────────────────────────────


def _done(db: Session, principal: Principal, target: str, payload: dict, **extra) -> dict:
    """Журнал и commit; ответ — новый rev черновика и результат действия."""
    draft = fd.current_draft(db)
    audit(db, principal, "stays_fund_version", target, payload)
    out = {"rev": draft.rev if draft else None, **extra}
    db.commit()
    return out


def _run(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except FundError as e:
        raise _err(e) from e


@router.post("/fund/draft")
def open_draft(payload: DraftIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    d = _run(fd.open_draft, db, payload.valid_from, principal.user.id, payload.note)
    return _done(db, principal, f"fund_draft:{d.id}", {"open": payload.valid_from.isoformat()},
                 id=d.id, valid_from=d.valid_from.isoformat())


@router.patch("/fund/draft")
def move_draft(payload: DraftMoveIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    _run(fd.move_draft_date, db, payload.rev, payload.valid_from)
    return _done(db, principal, "fund_draft", {"move": payload.valid_from.isoformat()},
                 valid_from=payload.valid_from.isoformat())


@router.delete("/fund/versions/{vid}")
def remove_version(vid: int, preview_flag: bool = PREVIEW, principal: Principal = Depends(SETUP),
                   db: Session = Depends(get_db)):
    """Удаление черновика или будущей версии и его предпросмотр (?preview=1) — одна операция, как
    публикация: удаление опубликованной версии перераспределяет брони, новый овербукинг без права
    stays.overbook — 409 (часть 2 §7)."""
    def op():
        fd.delete_version(db, vid)
        audit(db, principal, "stays_fund_version", f"fund_version:{vid}", {"delete": True})
        return {"ok": True}
    return run(db, op, preview_flag, None, principal)


def _data(payload: BaseModel) -> dict:
    return payload.model_dump(exclude={"rev"}, exclude_unset=True)


@router.post("/fund/draft/categories")
def create_category(payload: DraftCategoryIn, principal: Principal = Depends(SETUP),
                    db: Session = Depends(get_db)):
    cid = _run(fd.save_category, db, payload.rev, _data(payload), None)
    return _done(db, principal, f"fund_draft:category:{cid}", {"save": _data(payload)}, id=cid)


@router.put("/fund/draft/categories/{cid}")
def update_category(cid: int, payload: DraftCategoryIn, principal: Principal = Depends(SETUP),
                    db: Session = Depends(get_db)):
    _run(fd.save_category, db, payload.rev, _data(payload), cid)
    return _done(db, principal, f"fund_draft:category:{cid}", {"save": _data(payload)}, id=cid)


@router.delete("/fund/draft/categories/{cid}")
def remove_category(cid: int, rev: int = Query(), principal: Principal = Depends(SETUP),
                    db: Session = Depends(get_db)):
    _run(fd.retire_category, db, rev, cid)
    return _done(db, principal, f"fund_draft:category:{cid}", {"retire": True})


@router.post("/fund/draft/groups")
def create_group(payload: DraftGroupIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    gid = _run(fd.save_group, db, payload.rev, _data(payload), None)
    return _done(db, principal, f"fund_draft:group:{gid}", {"save": _data(payload)}, id=gid)


@router.put("/fund/draft/groups/{gid}")
def update_group(gid: int, payload: DraftGroupIn, principal: Principal = Depends(SETUP),
                 db: Session = Depends(get_db)):
    _run(fd.save_group, db, payload.rev, _data(payload), gid)
    return _done(db, principal, f"fund_draft:group:{gid}", {"save": _data(payload)}, id=gid)


@router.delete("/fund/draft/groups/{gid}")
def remove_group(gid: int, rev: int = Query(), principal: Principal = Depends(SETUP),
                 db: Session = Depends(get_db)):
    _run(fd.retire_group, db, rev, gid)
    return _done(db, principal, f"fund_draft:group:{gid}", {"retire": True})


@router.post("/fund/draft/units")
def create_unit(payload: DraftUnitIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    uid = _run(fd.save_unit, db, payload.rev, _data(payload), None)
    return _done(db, principal, f"fund_draft:unit:{uid}", {"save": _data(payload)}, id=uid)


@router.put("/fund/draft/units/{uid}")
def update_unit(uid: int, payload: DraftUnitIn, principal: Principal = Depends(SETUP),
                db: Session = Depends(get_db)):
    _run(fd.save_unit, db, payload.rev, _data(payload), uid)
    return _done(db, principal, f"fund_draft:unit:{uid}", {"save": _data(payload)}, id=uid)


@router.delete("/fund/draft/units/{uid}")
def remove_unit(uid: int, rev: int = Query(), principal: Principal = Depends(SETUP),
                db: Session = Depends(get_db)):
    _run(fd.retire_unit, db, rev, uid)
    return _done(db, principal, f"fund_draft:unit:{uid}", {"retire": True})


@router.post("/fund/draft/units/merge")
def merge_units(payload: MergeIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"rev", "unit_ids"}, exclude_unset=True)
    new_id = _run(fd.merge_units, db, payload.rev, payload.unit_ids, data)
    return _done(db, principal, f"fund_draft:unit:{new_id}",
                 {"merge": payload.unit_ids, "into": data}, id=new_id)


@router.post("/fund/draft/units/{uid}/split")
def split_unit(uid: int, payload: SplitIn, principal: Principal = Depends(SETUP),
               db: Session = Depends(get_db)):
    parts = [p.model_dump(exclude_unset=True) for p in payload.parts]
    ids = _run(fd.split_unit, db, payload.rev, uid, parts)
    return _done(db, principal, f"fund_draft:unit:{uid}", {"split": parts, "into": ids}, ids=ids)


@router.put("/fund/draft/flags")
def put_draft_flags(payload: FlagValueIn, principal: Principal = Depends(SETUP),
                    db: Session = Depends(get_db)):
    _run(fd.set_flag, db, payload.rev, payload.flag_id, payload.unit_ids, payload.value)
    return _done(db, principal, f"fund_draft:flag:{payload.flag_id}",
                 {"units": payload.unit_ids, "value": payload.value})


@router.post("/fund/draft/publish")
def publish_draft(payload: PublishIn, preview_flag: bool = PREVIEW, principal: Principal = Depends(SETUP),
                  db: Session = Depends(get_db)):
    """Публикация и её предпросмотр (?preview=1) — одна операция: предпросмотр откатывается
    (§4.3). rev сверяется в fd.publish под замком модуля."""
    transfers = [fd.Transfer(t.reservation_id, t.category_id) for t in payload.transfers]

    def op():
        res = fd.publish(db, principal, payload.rev, propagate=payload.propagate, transfers=transfers)
        v = res.version
        return {"version": {"id": v.id, "valid_from": v.valid_from.isoformat(), "rev": v.rev},
                "fund_diff": res.fund_diff, "propagated": res.propagated, "kept": res.kept,
                "skipped": res.skipped, "transfers": res.transfers}
    out = run(db, op, preview_flag, None, principal)
    added = out["diff"]["warnings_added"]
    # «unassigned» в ответе — брони без объекта: с части 2 это предупреждение overbooked
    out["result"]["affected"] = {"moved": out["diff"]["moved"],
                                 **{k: [w for w in added if w["kind"] == kind]
                                    for k, kind in (("unassigned", "overbooked"), ("pin_invalid", "pin_invalid"),
                                                    ("category_missing", "category_missing"))}}
    return out


# ── файл фонда (§9) ────────────────────────────────────────────────────────

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/fund/export", response_class=Response, responses={200: {"content": {XLSX: {}}}})
def export_fund(date: dt.date, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    """Фонд на дату файлом Excel — он же образец для загрузки (§9.1)."""
    data = fx.export_fund(_fund_on(db, date), list(db.scalars(select(UnitFlag))))
    return Response(content=data, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="fund-{date.isoformat()}.xlsx"'})


def _file_errors(errors: list[fx.FileError]) -> JSONResponse:
    return JSONResponse(status_code=422, content={"errors": [
        {"sheet": e.sheet, "row": e.row, "message": e.message} for e in errors]})


def _read_upload(file: UploadFile) -> bytes:
    cap = fx.MAX_FILE_BYTES
    if file.size is not None and file.size > cap:
        raise HTTPException(413, f"Файл больше {cap // 1024 // 1024} МБ")
    data = file.file.read(cap + 1)           # с запасом в байт: лимит до чтения файла целиком
    if len(data) > cap:
        raise HTTPException(413, f"Файл больше {cap // 1024 // 1024} МБ")
    return data


@router.post("/fund/import")
def import_fund(valid_from: dt.date = Form(...), file: UploadFile = File(...),
                principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    """«Загрузить как черновик с даты» (§9.3): открывает черновик на valid_from (409, если он уже
    есть) и применяет к нему файл. Ошибки файла — 422 {errors: [{sheet, row, message}]}, и тогда
    не остаётся ничего, даже черновика: всё — одна транзакция. flags — правки справочника флагов
    {created, renamed, recoloured}: он не версионируется, и они остаются и без черновика."""
    data = _read_upload(file)
    try:
        draft = fd.open_draft(db, valid_from, principal.user.id)
        parsed, errors = fx.parse_fund(data, known_unit_ids=set(snapshot_of(db, draft.id).units))
        if parsed is None:
            db.rollback()
            return _file_errors(errors)
        result, flags = fd.apply_file(db, draft.rev, parsed)
        change = asdict(result)
    except fd.FundFileError as e:
        db.rollback()
        return _file_errors(e.errors)
    except FundError as e:
        db.rollback()
        raise _err(e) from e
    names = {"unit": "label", "category": "code", "group": "title"}
    retired = [{"entity": entity, "id": e["id"], "name": e["before"].get(names[entity])}
               for entity, key in (("unit", "units"), ("group", "groups"), ("category", "categories"))
               for e in change[key] if e["kind"] == "retired"]
    counts = {key: {k: sum(e["kind"] == k for e in change[key]) for k in ("added", "changed", "retired")}
              for key in ("units", "categories", "groups")}
    audit(db, principal, "stays_fund_import", f"fund_draft:{draft.id}",
          {"valid_from": valid_from.isoformat(), "filename": file.filename, "counts": counts,
           "flags": flags, "units_flags_changed": len(change["flags"])})
    out = {"id": draft.id, "valid_from": draft.valid_from.isoformat(), "rev": draft.rev,
           "diff": change, "retired": retired, "flags": flags}
    db.commit()
    return out


# ── начальная загрузка (§9.3) ──────────────────────────────────────────────


class InProductionIn(BaseModel):
    value: bool


@router.post("/fund/reset")
def reset_fund(file: UploadFile = File(...), confirm: str = Form(""), fingerprint: str = Form(""),
               preview_flag: bool = PREVIEW, principal: Principal = Depends(RESET),
               db: Session = Depends(get_db)):
    """«Начальная загрузка (заменить всё)». ?preview=1 — что будет удалено и загружено,
    предупреждения и fingerprint; без него — замена: нужны confirm = «ЗАМЕНИТЬ» (иначе 422) и
    fingerprint предпросмотра (данные изменились — 409). Пока «в эксплуатации» — 409. Ошибки
    файла — 422 {errors}, и ничего не удалено. Ответ замены — имя копии и адрес её скачивания."""
    data = _read_upload(file)
    parsed, errors = fx.parse_fund(data)
    if parsed is None:
        return _file_errors(errors)
    try:
        if preview_flag:
            out = fr.preview(db, parsed)
            db.rollback()
            return out
        out = fr.initial_load(db, parsed, principal, fr.parse_fingerprint(fingerprint),
                              confirm=confirm, filename=file.filename or "")
    except fd.FundFileError as e:
        db.rollback()
        return _file_errors(e.errors)
    except FundError as e:
        db.rollback()
        raise _err(e) from e
    db.commit()
    return {**out, "backup_url": f"/api/stays/fund/backups/{out['backup']}"}


@router.get("/fund/backups/{name}", response_class=FileResponse, responses={200: {"content": {XLSX: {}}}})
def get_backup(name: str, principal: Principal = Depends(RESET), db: Session = Depends(get_db)):
    """Копия перед начальной загрузкой: имя строго stays-YYYYMMDD-HHMMSS.xlsx, без путей.
    В копии персональные данные гостей — скачивание в журнале аудита."""
    path = fr.backup_path(name)
    if path is None:
        raise HTTPException(404, "Копии нет")
    audit(db, principal, "stays_reset", f"backup:{name}", {"download": True})
    db.commit()
    return FileResponse(path, media_type=XLSX, filename=name)


@router.put("/fund/in-production")
def put_in_production(payload: InProductionIn, principal: Principal = Depends(RESET),
                      db: Session = Depends(get_db)):
    """Переключатель «Шахматка в эксплуатации»: включён — начальной загрузки нет (§9.3)."""
    value = fr.set_in_production(db, principal, payload.value)
    db.commit()
    return {"in_production": value}


# ── справочник флагов (вне черновика) ──────────────────────────────────────


def _flag_done(db: Session, principal: Principal, flag_id: int, payload: dict) -> dict:
    audit(db, principal, "stays_fund", f"flag:{flag_id}", payload)
    db.commit()
    return {"id": flag_id}


@router.post("/fund/flags")
def create_flag(payload: FlagIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    fid = _run(fd.save_flag, db, payload.model_dump(), None)
    return _flag_done(db, principal, fid, payload.model_dump())


@router.put("/fund/flags/{fid}")
def update_flag(fid: int, payload: FlagIn, principal: Principal = Depends(SETUP),
                db: Session = Depends(get_db)):
    _run(fd.save_flag, db, payload.model_dump(), fid)
    return _flag_done(db, principal, fid, payload.model_dump())


@router.put("/fund/flags/{fid}/archive")
def archive_flag(fid: int, payload: ArchiveIn, principal: Principal = Depends(SETUP),
                 db: Session = Depends(get_db)):
    _run(fd.archive_flag, db, fid, payload.archived)
    return _flag_done(db, principal, fid, {"archived": payload.archived})


@router.delete("/fund/flags/{fid}")
def remove_flag(fid: int, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    _run(fd.delete_flag, db, fid)
    return _flag_done(db, principal, fid, {"delete": True})


# ── справочник видов категорий (вне черновика) ─────────────────────────────


def _kind_done(db: Session, principal: Principal, kind_id: int, payload: dict) -> dict:
    audit(db, principal, "stays_fund", f"kind:{kind_id}", payload)
    db.commit()
    return {"id": kind_id}


@router.post("/fund/kinds")
def create_kind(payload: KindIn, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    kid = _run(fd.save_kind, db, payload.model_dump(), None)
    return _kind_done(db, principal, kid, payload.model_dump())


@router.put("/fund/kinds/{kid}")
def update_kind(kid: int, payload: KindIn, principal: Principal = Depends(SETUP),
                db: Session = Depends(get_db)):
    _run(fd.save_kind, db, payload.model_dump(), kid)
    return _kind_done(db, principal, kid, payload.model_dump())


@router.put("/fund/kinds/{kid}/archive")
def archive_kind(kid: int, payload: ArchiveIn, principal: Principal = Depends(SETUP),
                 db: Session = Depends(get_db)):
    _run(fd.archive_kind, db, kid, payload.archived)
    return _kind_done(db, principal, kid, {"archived": payload.archived})


@router.delete("/fund/kinds/{kid}")
def remove_kind(kid: int, principal: Principal = Depends(SETUP), db: Session = Depends(get_db)):
    _run(fd.delete_kind, db, kid)
    return _kind_done(db, principal, kid, {"delete": True})
