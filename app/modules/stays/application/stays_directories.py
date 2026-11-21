"""Справочники шахматки: метки, настраиваемые поля, сопровождающие, настройки, VIP-коды.

Справочники не версионируются — правка действует сразу. Каждая операция — одна транзакция
вместе с записью журнала аудита. Роутер проверяет право ``stays.setup``.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transactional
from app.modules.fund.application import fund
from app.modules.fund.application.fund_forms import EscortIn, FieldIn, LabelIn, SeedIn, SettingsIn
from app.modules.guests.application import guest_fields, guests, vip_codes
from app.modules.guests.application.catalog import VipCode

from . import reservations, stays_catalog


def overview(db: Session, *, with_staff: bool) -> dict:
    """Справочники одним ответом; ``with_staff`` — список сотрудников для экрана «Сопровождение»."""
    out = {"staff": None, **stays_catalog.list_fund(db, with_staff=with_staff)}
    out["vip_codes"] = [vip_codes.code_dict(c) for c in vip_codes.all_codes(db)]     # и архивные
    return out


def _write(db: Session, principal: Principal, target: str, before: dict, after: dict) -> None:
    audit(db, principal, "stays_fund", target, {"diff": fund.changes(before, after)})


@transactional
def save_label(db: Session, principal: Principal, payload: LabelIn, label_id: int | None) -> dict:
    row, before = stays_catalog.save_label(db, payload.model_dump(), label_id)
    after = fund.as_dict(row, stays_catalog.LABEL_FIELDS)
    _write(db, principal, f"label:{row.id}", before, after)
    return after


@transactional
def delete_label(db: Session, principal: Principal, label_id: int) -> dict:
    before = stays_catalog.delete_label(db, label_id)
    _write(db, principal, f"label:{label_id}", before, {k: None for k in before})
    return {"ok": True}


@transactional
def save_field(db: Session, principal: Principal, payload: FieldIn, field_id: int | None) -> dict:
    row, before = guest_fields.save_field(db, payload.model_dump(), field_id)
    after = guest_fields.field_dict(row)
    if bool(before.get("searchable")) != after["searchable"]:
        guests.reindex_search(db)          # флаг «искать по полю» меняет состав search_text
        reservations.reindex_search(db)
    _write(db, principal, f"field:{row.id}", before, after)
    return after


@transactional
def delete_field(db: Session, principal: Principal, field_id: int) -> dict:
    before = guest_fields.delete_field(db, field_id)
    _write(db, principal, f"field:{field_id}", before, {k: None for k in before})
    return {"ok": True}


@transactional
def set_escort(db: Session, principal: Principal, employee_id: int, payload: EscortIn) -> dict:
    row = stays_catalog.set_escort(db, employee_id, payload.active)
    after = {"employee_id": employee_id, "active": row.active}
    _write(db, principal, f"escort:{employee_id}", {}, after)
    return after


@transactional
def seed_escorts(db: Session, principal: Principal, payload: SeedIn) -> dict:
    added = stays_catalog.seed_escorts_from_positions(db, payload.position)
    _write(db, principal, "escorts:seed", {}, {"added": added})
    return {"added": added}


@transactional
def save_settings(db: Session, principal: Principal, payload: SettingsIn) -> dict:
    row, before = stays_catalog.save_settings(db, payload.special_factor, payload.daily_limit,
                                     payload.replacement_codes)
    after = fund.as_dict(row, stays_catalog.SETTINGS_FIELDS)
    _write(db, principal, "settings", before, after)
    return after


# ── справочник VIP-кодов ─────────────────────────────────────────────────────


def _code_audit(db: Session, principal: Principal, code_id: int, before: dict, after: dict) -> None:
    audit(db, principal, "stays_vip_code", f"vip_code:{code_id}", {"diff": fund.changes(before, after)})


def _code_state(db: Session, code_id: int | None) -> dict:
    row = db.get(VipCode, code_id) if code_id is not None else None
    return vip_codes.code_dict(row) if row else {}


@transactional
def save_vip_code(db: Session, principal: Principal, data: dict, code_id: int | None) -> dict:
    """``data`` — тело запроса; при правке только заданные поля (остальные остаются прежними)."""
    before = _code_state(db, code_id)
    rid = vip_codes.save_code(db, data, code_id)
    after = _code_state(db, rid)
    _code_audit(db, principal, rid, before, after)
    return after


@transactional
def archive_vip_code(db: Session, principal: Principal, code_id: int, archived: bool) -> dict:
    before = _code_state(db, code_id)
    vip_codes.archive_code(db, code_id, archived)
    after = _code_state(db, code_id)
    _code_audit(db, principal, code_id, before, after)
    return after


@transactional
def delete_vip_code(db: Session, principal: Principal, code_id: int) -> dict:
    before = _code_state(db, code_id)
    vip_codes.delete_code(db, code_id, used_elsewhere=reservations.vip_code_in_use(db, code_id))
    _code_audit(db, principal, code_id, before, {k: None for k in before})
    return {"id": code_id}
