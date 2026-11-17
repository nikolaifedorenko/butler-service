"""Прикладной слой справочников шахматки (шаг 4е-2): запись и аудит — одна транзакция."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.audit import AuditLog
from app.modules.stays.adapters.orm import CustomField, Label, VipCode
from app.modules.stays.application import stays_directories

from .helpers import API, uniq


def _break_audit(monkeypatch) -> None:
    def broken(*_a, **_k):
        raise RuntimeError("журнал недоступен")
    monkeypatch.setattr(stays_directories, "audit", broken)


def test_label_is_not_saved_when_audit_fails(admin_client, db, monkeypatch):
    _break_audit(monkeypatch)
    title = "метка-" + uniq()
    with pytest.raises(RuntimeError):
        admin_client.post(f"{API}/labels", json={"title": title, "color": "#112233"})
    db.rollback()
    assert db.scalar(select(Label).where(Label.title == title)) is None


def test_vip_code_is_not_saved_when_audit_fails(admin_client, db, monkeypatch):
    _break_audit(monkeypatch)
    with pytest.raises(RuntimeError):
        admin_client.post(f"{API}/vip-codes", json={"code": "8", "title": "не сохранится"})
    db.rollback()
    assert db.scalar(select(VipCode).where(VipCode.title == "не сохранится")) is None


def test_field_create_update_delete_and_audit(admin_client, db):
    code = "f" + uniq().lower()
    r = admin_client.post(f"{API}/fields", json={"target": "guest", "code": code, "title": "Поле",
                                                 "kind": "choice", "choices": [" а ", ""]})
    assert r.status_code == 200 and r.json()["choices"] == ["а"]
    fid = r.json()["id"]
    assert admin_client.delete(f"{API}/fields/{fid}").json() == {"ok": True}
    assert admin_client.delete(f"{API}/fields/{fid}").status_code == 422
    db.rollback()
    assert db.get(CustomField, fid) is None
    actions = [a.target for a in db.scalars(select(AuditLog).where(AuditLog.target == f"field:{fid}"))]
    assert actions == [f"field:{fid}", f"field:{fid}"]


def test_directories_overview_has_staff_only_for_setup(admin_client, manager_client):
    assert isinstance(admin_client.get(f"{API}/fund").json()["staff"], list)
    body = manager_client.get(f"{API}/fund").json()
    assert set(body) >= {"labels", "fields", "escorts", "settings", "in_production", "vip_codes", "staff"}


def test_vip_code_conflicts_and_unknown(admin_client):
    code = admin_client.post(f"{API}/vip-codes", json={"code": "6", "title": uniq()})
    if code.status_code == 200:
        cid = code.json()["id"]
        assert admin_client.post(f"{API}/vip-codes", json={"code": "6"}).status_code == 409
        assert admin_client.delete(f"{API}/vip-codes/{cid}").json() == {"id": cid}
    assert admin_client.delete(f"{API}/vip-codes/99999").status_code == 422
