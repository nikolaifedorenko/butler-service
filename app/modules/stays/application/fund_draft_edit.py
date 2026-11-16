"""Запись черновика фонда и версий: операции со сверкой ревизии, журналом и предпросмотром (§4, §9.2).

Каждая запись черновика несёт ``rev`` (оптимистичная блокировка: 409 при расхождении) и
возвращает новый ``rev``. Публикация и удаление версии — операции с предпросмотром: разница
по броням показывается до сохранения. Роутер проверяет право ``stays.setup``.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transactional

from . import fund_drafts as fd
from . import fund_xlsx as fx
from .fund_forms import (
    DraftCategoryIn,
    DraftGroupIn,
    DraftIn,
    DraftMoveIn,
    DraftUnitIn,
    FlagValueIn,
    MergeIn,
    PublishIn,
    SplitIn,
)
from .fund_versions import snapshot_of
from .previewed import run_previewed


def _done(db: Session, principal: Principal, target: str, payload: dict, **extra) -> dict:
    """Журнал; ответ — новый rev черновика и результат действия."""
    draft = fd.current_draft(db)
    audit(db, principal, "stays_fund_version", target, payload)
    return {"rev": draft.rev if draft else None, **extra}


def _data(payload: BaseModel) -> dict:
    return payload.model_dump(exclude={"rev"}, exclude_unset=True)


@transactional
def open_draft(db: Session, principal: Principal, payload: DraftIn) -> dict:
    d = fd.open_draft(db, payload.valid_from, principal.user.id, payload.note)
    return _done(db, principal, f"fund_draft:{d.id}", {"open": payload.valid_from.isoformat()},
                 id=d.id, valid_from=d.valid_from.isoformat())


@transactional
def move_draft(db: Session, principal: Principal, payload: DraftMoveIn) -> dict:
    fd.move_draft_date(db, payload.rev, payload.valid_from)
    return _done(db, principal, "fund_draft", {"move": payload.valid_from.isoformat()},
                 valid_from=payload.valid_from.isoformat())


def delete_version(db: Session, principal: Principal, version_id: int, *, preview_only: bool) -> dict:
    """Удаление черновика или будущей версии и его предпросмотр — одна операция, как
    публикация: удаление опубликованной версии перераспределяет брони, новый овербукинг без
    права ``stays.overbook`` — 409 (часть 2 §7)."""
    def operation():
        fd.delete_version(db, version_id)
        audit(db, principal, "stays_fund_version", f"fund_version:{version_id}", {"delete": True})
        return {"ok": True}
    return run_previewed(db, operation, preview_only=preview_only,
                         may_overbook="stays.overbook" in principal.gate_permissions)


@transactional
def save_category(db: Session, principal: Principal, payload: DraftCategoryIn, category_id: int | None) -> dict:
    cid = fd.save_category(db, payload.rev, _data(payload), category_id)
    return _done(db, principal, f"fund_draft:category:{cid}", {"save": _data(payload)}, id=cid)


@transactional
def retire_category(db: Session, principal: Principal, rev: int, category_id: int) -> dict:
    fd.retire_category(db, rev, category_id)
    return _done(db, principal, f"fund_draft:category:{category_id}", {"retire": True})


@transactional
def save_group(db: Session, principal: Principal, payload: DraftGroupIn, group_id: int | None) -> dict:
    gid = fd.save_group(db, payload.rev, _data(payload), group_id)
    return _done(db, principal, f"fund_draft:group:{gid}", {"save": _data(payload)}, id=gid)


@transactional
def retire_group(db: Session, principal: Principal, rev: int, group_id: int) -> dict:
    fd.retire_group(db, rev, group_id)
    return _done(db, principal, f"fund_draft:group:{group_id}", {"retire": True})


@transactional
def save_unit(db: Session, principal: Principal, payload: DraftUnitIn, unit_id: int | None) -> dict:
    uid = fd.save_unit(db, payload.rev, _data(payload), unit_id)
    return _done(db, principal, f"fund_draft:unit:{uid}", {"save": _data(payload)}, id=uid)


@transactional
def retire_unit(db: Session, principal: Principal, rev: int, unit_id: int) -> dict:
    fd.retire_unit(db, rev, unit_id)
    return _done(db, principal, f"fund_draft:unit:{unit_id}", {"retire": True})


@transactional
def merge_units(db: Session, principal: Principal, payload: MergeIn) -> dict:
    data = payload.model_dump(exclude={"rev", "unit_ids"}, exclude_unset=True)
    new_id = fd.merge_units(db, payload.rev, payload.unit_ids, data)
    return _done(db, principal, f"fund_draft:unit:{new_id}",
                 {"merge": payload.unit_ids, "into": data}, id=new_id)


@transactional
def split_unit(db: Session, principal: Principal, unit_id: int, payload: SplitIn) -> dict:
    parts = [p.model_dump(exclude_unset=True) for p in payload.parts]
    ids = fd.split_unit(db, payload.rev, unit_id, parts)
    return _done(db, principal, f"fund_draft:unit:{unit_id}", {"split": parts, "into": ids}, ids=ids)


@transactional
def set_flags(db: Session, principal: Principal, payload: FlagValueIn) -> dict:
    fd.set_flag(db, payload.rev, payload.flag_id, payload.unit_ids, payload.value)
    return _done(db, principal, f"fund_draft:flag:{payload.flag_id}",
                 {"units": payload.unit_ids, "value": payload.value})


def publish(db: Session, principal: Principal, payload: PublishIn, *, preview_only: bool) -> dict:
    """Публикация и её предпросмотр — одна операция: предпросмотр откатывается (§4.3). ``rev``
    сверяется в ``fd.publish`` под замком модуля."""
    transfers = [fd.Transfer(t.reservation_id, t.category_id) for t in payload.transfers]

    def operation():
        res = fd.publish(db, principal, payload.rev, propagate=payload.propagate, transfers=transfers)
        v = res.version
        return {"version": {"id": v.id, "valid_from": v.valid_from.isoformat(), "rev": v.rev},
                "fund_diff": res.fund_diff, "propagated": res.propagated, "kept": res.kept,
                "skipped": res.skipped, "transfers": res.transfers}
    out = run_previewed(db, operation, preview_only=preview_only,
                        may_overbook="stays.overbook" in principal.gate_permissions)
    added = out["diff"]["warnings_added"]
    # «unassigned» в ответе — брони без объекта: с части 2 это предупреждение overbooked
    out["result"]["affected"] = {"moved": out["diff"]["moved"],
                                 **{k: [w for w in added if w["kind"] == kind]
                                    for k, kind in (("unassigned", "overbooked"), ("pin_invalid", "pin_invalid"),
                                                    ("category_missing", "category_missing"))}}
    return out


@transactional
def import_file(db: Session, principal: Principal, valid_from: dt.date, filename: str | None,
                data: bytes) -> dict:
    """«Загрузить как черновик с даты» (§9.3): открывает черновик на ``valid_from`` (409, если
    он уже есть) и применяет к нему файл. Ошибки файла — ``FundFileError`` (422 со списком), и
    тогда не остаётся ничего, даже черновика: всё — одна транзакция. ``flags`` — правки
    справочника флагов {created, renamed, recoloured}: справочник не версионируется."""
    draft = fd.open_draft(db, valid_from, principal.user.id)
    parsed, errors = fx.parse_fund(data, known_unit_ids=set(snapshot_of(db, draft.id).units))
    if parsed is None:
        raise fd.FundFileError(errors)
    result, flags = fd.apply_file(db, draft.rev, parsed)
    change = asdict(result)
    names = {"unit": "label", "category": "code", "group": "title"}
    retired = [{"entity": entity, "id": e["id"], "name": e["before"].get(names[entity])}
               for entity, key in (("unit", "units"), ("group", "groups"), ("category", "categories"))
               for e in change[key] if e["kind"] == "retired"]
    counts = {key: {k: sum(e["kind"] == k for e in change[key]) for k in ("added", "changed", "retired")}
              for key in ("units", "categories", "groups")}
    audit(db, principal, "stays_fund_import", f"fund_draft:{draft.id}",
          {"valid_from": valid_from.isoformat(), "filename": filename, "counts": counts,
           "flags": flags, "units_flags_changed": len(change["flags"])})
    return {"id": draft.id, "valid_from": draft.valid_from.isoformat(), "rev": draft.rev,
            "diff": change, "retired": retired, "flags": flags}
