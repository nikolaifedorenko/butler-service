"""Прикладной слой гостей (шаг 4е-3): запись и аудит — одна транзакция, отказы доступа — 403."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.audit import AuditLog
from app.modules.guests.application.catalog import Guest, GuestLink
from app.modules.stays.application import guest_edit
from tests.stays.helpers import API, make_guest, uniq


def test_guest_is_not_saved_when_audit_fails(manager_client, db, monkeypatch):
    def broken(*_a, **_k):
        raise RuntimeError("журнал недоступен")
    monkeypatch.setattr(guest_edit, "audit", broken)
    last = "Откат" + uniq()
    with pytest.raises(RuntimeError):
        manager_client.post(f"{API}/guests", json={"last_name": last})
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Guest).where(Guest.last_name == last)) == 0


def test_link_with_new_guest_is_all_or_nothing(manager_client, db):
    """Второй родитель не существует: не остаётся ни новой карточки, ни связи, ни журнала."""
    g = make_guest(manager_client)
    last = "Новичок" + uniq()
    links = db.scalar(select(func.count()).select_from(GuestLink))
    audit_before = db.scalar(select(func.count()).select_from(AuditLog))
    r = manager_client.post(f"{API}/guests/{g['id']}/links", json={
        "new_guest": {"last_name": last}, "kind": "parent", "other_is_parent": False, "also_parent_id": 99999999})
    assert r.status_code == 422
    db.rollback()
    assert db.scalar(select(func.count()).select_from(Guest).where(Guest.last_name == last)) == 0
    assert db.scalar(select(func.count()).select_from(GuestLink)) == links
    assert db.scalar(select(func.count()).select_from(AuditLog)) == audit_before


def test_merge_preview_keeps_both_profiles(manager_client, db):
    keep, drop = make_guest(manager_client), make_guest(manager_client)
    r = manager_client.post(f"{API}/guests/merge", params={"preview": 1},
                            json={"keep_id": keep["id"], "drop_id": drop["id"]})
    assert r.status_code == 200
    body = r.json()
    assert body["preview"] is True and body["overbook_refused"] is None and set(body["diff"]) >= {"moved"}
    db.rollback()
    assert db.get(Guest, drop["id"]) is not None


def test_update_without_code_change_has_no_diff(manager_client):
    g = make_guest(manager_client)
    card = manager_client.get(f"{API}/guests/{g['id']}").json()
    body = {k: card[k] for k in ("last_name", "first_name", "middle_name", "email", "special", "vip_code_id",
                                 "note", "fields", "special_dates", "birth_date", "phone", "preferences")}
    out = manager_client.put(f"{API}/guests/{g['id']}", json={**body, "note": "правка"}).json()
    assert out["diff"] is None and out["preview"] is False and out["updated_reservations"] == 0
    assert out["guest"]["note"] == "правка"


def test_unknown_guest_is_404_for_card_and_422_for_update(manager_client):
    assert manager_client.get(f"{API}/guests/99999999").status_code == 404
    card = {"last_name": "Икс"}
    assert manager_client.put(f"{API}/guests/99999999", json=card).status_code == 422
