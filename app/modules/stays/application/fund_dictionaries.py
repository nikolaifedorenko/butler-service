"""Справочники флагов объектов и видов категорий: вне черновика, меняются сразу (§3, §4).

Справочники не версионируются, поэтому правка действует без публикации. Роутер проверяет
право ``stays.setup``.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transactional

from . import fund_drafts as fd
from .fund_forms import FlagIn, KindIn


def _done(db: Session, principal: Principal, target: str, payload: dict, row_id: int) -> dict:
    audit(db, principal, "stays_fund", target, payload)
    return {"id": row_id}


@transactional
def save_flag(db: Session, principal: Principal, payload: FlagIn, flag_id: int | None) -> dict:
    fid = fd.save_flag(db, payload.model_dump(), flag_id)
    return _done(db, principal, f"flag:{fid}", payload.model_dump(), fid)


@transactional
def archive_flag(db: Session, principal: Principal, flag_id: int, archived: bool) -> dict:
    fd.archive_flag(db, flag_id, archived)
    return _done(db, principal, f"flag:{flag_id}", {"archived": archived}, flag_id)


@transactional
def delete_flag(db: Session, principal: Principal, flag_id: int) -> dict:
    fd.delete_flag(db, flag_id)
    return _done(db, principal, f"flag:{flag_id}", {"delete": True}, flag_id)


@transactional
def save_kind(db: Session, principal: Principal, payload: KindIn, kind_id: int | None) -> dict:
    kid = fd.save_kind(db, payload.model_dump(), kind_id)
    return _done(db, principal, f"kind:{kid}", payload.model_dump(), kid)


@transactional
def archive_kind(db: Session, principal: Principal, kind_id: int, archived: bool) -> dict:
    fd.archive_kind(db, kind_id, archived)
    return _done(db, principal, f"kind:{kind_id}", {"archived": archived}, kind_id)


@transactional
def delete_kind(db: Session, principal: Principal, kind_id: int) -> dict:
    fd.delete_kind(db, kind_id)
    return _done(db, principal, f"kind:{kind_id}", {"delete": True}, kind_id)
