"""Публикация версии фонда и удаление версии: данные меняет ``fund_drafts``, а здесь — то, что
знает о бронях: перевод броней на категорию, пересчёт размещения, журнал и предпросмотр (§4.3, §4.4).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal

from ..adapters.orm import FundVersion, Reservation
from . import allocation, reservations
from . import fund_drafts as fd
from .fund import FundError
from .fund_forms import PublishIn
from .fund_versions import fund_on
from .previewed import run_previewed


@dataclass(frozen=True)
class Transfer:
    reservation_id: int
    category_id: int


def _transfer(db: Session, principal, version: FundVersion, t: Transfer, categories: set[int]) -> dict:
    """Заезд с D и позже — бронь целиком в категорию; бронь, живущая на D, — переезд с D.
    Записывается тем же путём, что и правка формы: журнал брони «было → стало»."""
    day = version.valid_from
    r = db.get(Reservation, t.reservation_id)
    if r is None:
        raise FundError("бронь для перевода не найдена")
    who = f"бронь {r.number or r.id}"
    if t.category_id not in categories:
        raise FundError(f"{who}: категории перевода нет в фонде с {day:%d.%m.%Y}")
    if r.check_out <= day:
        raise FundError(f"{who}: выезд до {day:%d.%m.%Y} — переводить нечего")
    whole = r.check_in >= day
    if whole:
        doc = reservations.doc_of(db, r, category_id=t.category_id)
    else:
        doc = reservations.doc_of(db, r)
        doc["moves"] = sorted([m for m in doc["moves"] if m["move_date"] != day]
                              + [{"move_date": day, "category_id": t.category_id}], key=lambda m: m["move_date"])
    # члены группы получают ту же категорию и переезды (save_reservation) — журнал и им
    group = list(db.scalars(select(Reservation).where(Reservation.group_id == r.group_id,
                                                      Reservation.id != r.id))) if r.group_id else []
    others = [(m, reservations.reservation_snapshot(db, m)) for m in group]
    saved, before = reservations.save_reservation(db, doc, r.id, r.version)
    for m, was in [(saved, before), *others]:
        change = reservations.diff_of(was, db, m)
        if change or m is saved:
            audit(db, principal, "stays_reservation", f"reservation:{m.id}",
                  {"diff": change, "fund_version": version.id})
    return {"reservation_id": saved.id, "number": saved.number, "category_id": t.category_id,
            "since": None if whole else day.isoformat()}


def publish(db: Session, principal, rev: int | None = None, propagate: bool = True,
            transfers: Sequence[Transfer] = ()) -> fd.PublishResult:
    """``rev`` — ревизия, которую видел автор; сверяется под замком модуля, как в каждой записи.
    ``propagate`` — перенести правки в опубликованные версии после даты черновика (§4.4);
    ``transfers`` — перевод броней на категорию с даты версии (§4.3). Всё — одной транзакцией."""
    out = fd.publish_data(db, rev, propagate)
    version = out.version
    day = version.valid_from
    db.info.pop(allocation.CACHE_KEY, None)             # фонд другой — прежнее состояние распределения не годится
    if transfers:
        categories = set(fund_on(db, day).categories)
        out.transfers = [_transfer(db, principal, version, t, categories) for t in transfers]
    allocation.run_allocation(db)
    audit(db, principal, "stays_fund_version", f"fund_version:{version.id}",
          {"valid_from": day.isoformat(), "diff": out.fund_diff, "propagated": out.propagated, "kept": out.kept,
           "skipped": out.skipped, "transfers": out.transfers})
    return out


def delete_version(db: Session, version_id: int) -> None:
    """Удалить версию или черновик; удаление опубликованной версии перераспределяет брони."""
    if fd.delete_version_data(db, version_id):
        allocation.run_allocation(db)


def _may_overbook(principal: Principal) -> bool:
    return "stays.overbook" in principal.gate_permissions


def publish_previewed(db: Session, principal: Principal, payload: PublishIn, *, preview_only: bool) -> dict:
    """Публикация и её предпросмотр — одна операция: предпросмотр откатывается (§4.3). ``rev``
    сверяется в ``fd.publish_data`` под замком модуля."""
    transfers = [Transfer(t.reservation_id, t.category_id) for t in payload.transfers]

    def operation():
        res = publish(db, principal, payload.rev, propagate=payload.propagate, transfers=transfers)
        v = res.version
        return {"version": {"id": v.id, "valid_from": v.valid_from.isoformat(), "rev": v.rev},
                "fund_diff": res.fund_diff, "propagated": res.propagated, "kept": res.kept,
                "skipped": res.skipped, "transfers": res.transfers}
    out = run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal))
    added = out["diff"]["warnings_added"]
    # «unassigned» в ответе — брони без объекта: с части 2 это предупреждение overbooked
    out["result"]["affected"] = {"moved": out["diff"]["moved"],
                                 **{k: [w for w in added if w["kind"] == kind]
                                    for k, kind in (("unassigned", "overbooked"), ("pin_invalid", "pin_invalid"),
                                                    ("category_missing", "category_missing"))}}
    return out


def delete_previewed(db: Session, principal: Principal, version_id: int, *, preview_only: bool) -> dict:
    """Удаление черновика или будущей версии и его предпросмотр — одна операция, как публикация:
    удаление опубликованной версии перераспределяет брони, новый овербукинг без права
    ``stays.overbook`` — 409 (часть 2 §7)."""
    def operation():
        delete_version(db, version_id)
        audit(db, principal, "stays_fund_version", f"fund_version:{version_id}", {"delete": True})
        return {"ok": True}
    return run_previewed(db, operation, preview_only=preview_only, may_overbook=_may_overbook(principal))
