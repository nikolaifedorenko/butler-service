"""Прикладной слой броней, блоков и OOO (шаг 4е-4): запись и аудит — одна транзакция,
предпросмотр ничего не сохраняет, отказы несут статус класса ошибки."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.errors import Validation
from app.modules.board.application import views
from app.modules.stays.adapters.orm import Block, Ooo, Reservation, StayGroup
from app.modules.stays.application import block_edit, ooo_edit, reservation_edit
from app.modules.stays.application.previewed import OverbookRefusedError

from .helpers import API, create_res, make_category, make_guest, res_body, uniq


def _broken_audit(module, monkeypatch) -> None:
    def broken(*_a, **_k):
        raise RuntimeError("журнал недоступен")
    monkeypatch.setattr(module, "audit", broken)


def test_view_error_is_a_validation_error():
    assert issubclass(views.ViewError, Validation) and issubclass(views.ViewError, ValueError)
    assert views.ViewError("текст").status_code == 422


def test_overbook_refusal_carries_preview_in_detail():
    e = OverbookRefusedError("нет объекта", {"moved": []})
    assert e.status_code == 409 and e.detail == {"message": "нет объекта", "overbook": True, "diff": {"moved": []}}


def test_group_is_not_saved_when_audit_fails(manager_client, db, monkeypatch):
    _broken_audit(reservation_edit, monkeypatch)
    before = db.scalar(select(func.count()).select_from(StayGroup))
    with pytest.raises(RuntimeError):
        manager_client.post(f"{API}/groups", json={"title": "Откат"})
    db.rollback()
    assert db.scalar(select(func.count()).select_from(StayGroup)) == before


def test_reservation_is_not_saved_when_audit_fails(manager_client, manager_role_client, db, monkeypatch):
    cat = make_category(manager_role_client, n_units=1)
    guest = make_guest(manager_client)
    number = "R" + uniq()
    _broken_audit(reservation_edit, monkeypatch)
    body = res_body(cat, "2046-05-10", "2046-05-12", [(guest["id"], "main", None, None)], number=number)
    with pytest.raises(RuntimeError):
        manager_client.post(f"{API}/reservations", json=body)
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Reservation).where(Reservation.number == number)) == 0


def test_reservation_preview_saves_nothing(manager_client, manager_role_client, db):
    cat = make_category(manager_role_client, n_units=1)
    guest = make_guest(manager_client)
    number = "R" + uniq()
    body = res_body(cat, "2046-06-10", "2046-06-12", [(guest["id"], "main", None, None)], number=number)
    r = manager_client.post(f"{API}/reservations", params={"preview": 1}, json=body)
    assert r.status_code == 200 and r.json()["preview"] is True and r.json()["overbook_refused"] is None
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Reservation).where(Reservation.number == number)) == 0


def test_reservation_update_requires_version_and_unknown_is_422(manager_client, manager_role_client):
    cat = make_category(manager_role_client, n_units=1)
    guest = make_guest(manager_client)
    res = create_res(manager_client, cat, "2046-07-10", "2046-07-12", [(guest["id"], "main", None, None)])
    body = {k: res[k] for k in ("number", "check_in", "check_out", "category_id", "occupants")}
    assert manager_client.put(f"{API}/reservations/{res['id']}", json=body).status_code == 422
    stale = manager_client.put(f"{API}/reservations/{res['id']}", json={**body, "version": res["version"] + 9})
    assert stale.status_code == 409
    assert manager_client.put(f"{API}/reservations/99999999", json={**body, "version": 0}).status_code == 422
    assert manager_client.get(f"{API}/reservations/99999999").status_code == 404
    assert manager_client.get(f"{API}/reservations/99999999/cohabit").status_code == 404


def test_block_is_not_saved_when_audit_fails_and_preview_saves_nothing(manager_client, db, monkeypatch):
    title = "Блок" + uniq()
    body = {"title": title, "start": "2046-08-01", "end": "2046-08-03", "grid": {}}
    assert manager_client.post(f"{API}/blocks", params={"preview": 1}, json=body).status_code == 200
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Block).where(Block.title == title)) == 0
    _broken_audit(block_edit, monkeypatch)
    with pytest.raises(RuntimeError):
        manager_client.post(f"{API}/blocks", json=body)
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Block).where(Block.title == title)) == 0


def test_ooo_is_not_saved_when_audit_fails(manager_client, manager_role_client, db, monkeypatch):
    cat = make_category(manager_role_client, n_units=1)
    unit = cat["units"][0]["id"]
    _broken_audit(ooo_edit, monkeypatch)
    with pytest.raises(RuntimeError):
        manager_client.post(f"{API}/ooo", json={"unit_id": unit, "start": "2046-09-01", "end": "2046-09-03"})
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Ooo).where(Ooo.unit_id == unit)) == 0
