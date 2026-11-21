"""Чтение версий фонда: снимок на дату, список версий, разница черновика, файл фонда (§4, §9.1).

Чтение — тем, кто видит шахматку; запись черновика — ``fund_draft_edit.py``.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, Validation
from app.core.identity import User
from app.core.time import local_iso

from ..adapters.orm import FundVersion, UnitFlag, UnitLineage
from . import fund_drafts as fd
from . import fund_xlsx as fx
from .fund_versions import FundSnapshot, fund_on, kind_dict, kinds, snapshot_of


def fund_at(db: Session, date: dt.date) -> FundSnapshot:
    """Фонд на дату. Дата раньше первой версии — ошибка ввода (422)."""
    try:
        return fund_on(db, date)
    except LookupError as e:
        raise Validation(str(e)) from e


def _version_dict(v: FundVersion) -> dict:
    return {"id": v.id, "valid_from": v.valid_from.isoformat(), "status": v.status, "rev": v.rev}


def _snapshot_dict(db: Session, version: FundVersion, snap: FundSnapshot) -> dict:
    return {
        "version": _version_dict(version),
        "categories": [{"id": c.id, "code": c.code, "title": c.title, "kind_id": c.kind_id, "weight": c.weight,
                        "escorted": c.escorted, "sort_order": c.sort_order}
                       for c in sorted(snap.categories.values(), key=lambda c: (c.sort_order, c.id))],
        "groups": [{"id": g.id, "parent_id": g.parent_id, "title": g.title, "sort_order": g.sort_order,
                    "escorted": g.escorted, "path": list(g.path)}
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


def snapshot(db: Session, date: Optional[dt.date], version_id: Optional[int]) -> dict:
    """Фонд на дату или версия по номеру — ровно одно из двух."""
    if (date is None) == (version_id is None):
        raise Validation("Укажите ровно один параметр: date или version_id")
    if version_id is not None:
        version = db.get(FundVersion, version_id)
        if version is None:
            raise NotFound("Версии фонда нет")
        snap = snapshot_of(db, version_id)
    else:
        assert date is not None         # ровно один из параметров — проверено выше
        snap = fund_at(db, date)
        version = db.get(FundVersion, snap.version_id)
        if version is None:
            raise NotFound("Версии фонда нет")
    return _snapshot_dict(db, version, snap)


def versions(db: Session) -> list[dict]:
    rows = db.execute(select(FundVersion, User.username)
                      .outerjoin(User, User.id == FundVersion.author_id)
                      .order_by(FundVersion.valid_from, FundVersion.id)).all()
    return [{"id": v.id, "valid_from": v.valid_from.isoformat(), "status": v.status, "author": name,
             "note": v.note, "published_at": local_iso(v.published_at, "auto")}
            for v, name in rows]


def draft_diff(db: Session) -> dict:
    """Что изменено в черновике против его базы."""
    draft = fd.current_draft(db)
    if draft is None:
        raise Conflict("Черновика фонда нет")
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


def export_file(db: Session, date: dt.date) -> tuple[bytes, str]:
    """Фонд на дату файлом Excel — он же образец для загрузки (§9.1): содержимое и имя файла."""
    data = fx.export_fund(fund_at(db, date), list(db.scalars(select(UnitFlag))))
    return data, f"fund-{date.isoformat()}.xlsx"
