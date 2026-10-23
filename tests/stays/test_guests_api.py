"""Шахматка, задача 7: профили гостей, связи «кто кому», поиск, видимость полей."""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select

from app.core.audit import AuditLog
from app.modules.stays.application.guests import format_phone, normalize_phone

API = "/api/stays"


def _uniq() -> str:
    return uuid.uuid4().hex[:6]


def _guest(c, last="Орлов", **kw):
    r = c.post(f"{API}/guests", json={"last_name": last, "first_name": "Андрей", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_normalize_phone():
    assert normalize_phone("8 (916) 123-45-67") == "+79161234567"
    assert normalize_phone("9161234567") == "+79161234567"
    assert normalize_phone("+44 20 7946 0958") == "+442079460958"
    assert normalize_phone("") == ""
    assert format_phone("+79161234567") == "+7 916 123-45-67"


def test_bad_phone_refused(manager_client):
    r = manager_client.post(f"{API}/guests", json={"last_name": "Икс", "phone": "12"})
    assert r.status_code == 422 and r.json()["detail"] == "Телефон должен быть в формате +7 999 123-45-67"


def test_phone_normalized_on_save(manager_client):
    g = _guest(manager_client, phone="8 (916) 123-45-67")
    assert g["phone"] == "+79161234567"


def test_level_validated(manager_client):
    r = manager_client.post(f"{API}/guests", json={"last_name": "Икс", "level": "gold"})
    assert r.status_code == 422


def test_link_labels_both_sides(manager_client):
    parent, child = _guest(manager_client, "Родитель" + _uniq()), _guest(manager_client, "Ребёнок" + _uniq())
    r = manager_client.post(f"{API}/guests/{parent['id']}/links", json={"guest_id": child["id"], "kind": "child"})
    assert r.status_code == 200, r.text
    a = manager_client.get(f"{API}/guests/{parent['id']}").json()["links"]
    b = manager_client.get(f"{API}/guests/{child['id']}").json()["links"]
    assert [(x["guest_id"], x["label"]) for x in a] == [(child["id"], "ребёнок")]
    assert [(x["guest_id"], x["label"]) for x in b] == [(parent["id"], "родитель")]
    assert manager_client.delete(f"{API}/guest-links/{a[0]['id']}").status_code == 200
    assert manager_client.get(f"{API}/guests/{parent['id']}").json()["links"] == []


def test_link_to_self_refused(manager_client):
    g = _guest(manager_client)
    r = manager_client.post(f"{API}/guests/{g['id']}/links", json={"guest_id": g["id"], "kind": "spouse"})
    assert r.status_code == 422 and r.json()["detail"] == "Гость не может быть связан сам с собой"


def test_duplicate_link_refused(manager_client):
    a, b = _guest(manager_client), _guest(manager_client)
    body = {"guest_id": b["id"], "kind": "spouse"}
    assert manager_client.post(f"{API}/guests/{a['id']}/links", json=body).status_code == 200
    r = manager_client.post(f"{API}/guests/{a['id']}/links", json=body)
    assert r.status_code == 409 and r.json()["detail"] == "Такая связь уже есть"


def test_search_cyrillic_case_insensitive(manager_client):
    last = "Ёлкина" + _uniq()
    g = _guest(manager_client, last)
    found = manager_client.get(f"{API}/guests", params={"q": last.lower()}).json()
    assert [x["id"] for x in found] == [g["id"]]


def test_search_by_phone_digits(manager_client):
    g = _guest(manager_client, "Телефонов" + _uniq(), phone="+7 903 555-12-34")
    found = manager_client.get(f"{API}/guests", params={"q": "8 903 555"}).json()
    assert g["id"] in [x["id"] for x in found]


def test_search_by_searchable_field_only(manager_role_client, manager_client):
    u = _uniq()
    for code, searchable in ((f"club{u}", True), (f"secret{u}", False)):
        r = manager_role_client.post(f"{API}/fields", json={
            "target": "guest", "code": code, "title": code, "kind": "text", "searchable": searchable})
        assert r.status_code == 200, r.text
    g = _guest(manager_client, fields={f"club{u}": f"gold{u}", f"secret{u}": f"hidden{u}"})
    assert [x["id"] for x in manager_client.get(f"{API}/guests", params={"q": f"gold{u}"}).json()] == [g["id"]]
    assert manager_client.get(f"{API}/guests", params={"q": f"hidden{u}"}).json() == []


def test_unknown_or_bad_field_refused(manager_role_client, manager_client):
    u = _uniq()
    manager_role_client.post(f"{API}/fields", json={"target": "guest", "code": f"vip{u}", "title": "x",
                                                    "kind": "choice", "choices": ["Gold"]})
    r = manager_client.post(f"{API}/guests", json={"last_name": "Икс", "fields": {f"nope{u}": "1"}})
    assert r.status_code == 422 and r.json()["detail"] == f"Неизвестное поле: nope{u}"
    r = manager_client.post(f"{API}/guests", json={"last_name": "Икс", "fields": {f"vip{u}": "Silver"}})
    assert r.status_code == 422 and r.json()["detail"] == "Поле «x»: значения нет в списке"


def test_field_reindex_when_made_searchable(manager_role_client, manager_client):
    u = _uniq()
    f = manager_role_client.post(f"{API}/fields", json={"target": "guest", "code": f"yacht{u}", "title": "Яхта",
                                                        "kind": "text"}).json()
    g = _guest(manager_client, fields={f"yacht{u}": f"Пегас{u}"})
    assert manager_client.get(f"{API}/guests", params={"q": f"пегас{u}"}).json() == []
    manager_role_client.put(f"{API}/fields/{f['id']}", json={**f, "searchable": True})
    assert [x["id"] for x in manager_client.get(f"{API}/guests", params={"q": f"пегас{u}"}).json()] == [g["id"]]


def test_list_has_no_contact_fields(manager_client):
    _guest(manager_client, "Скрытов" + _uniq(), phone="+79160000001", birth_date="1980-01-02")
    rows = manager_client.get(f"{API}/guests", params={"q": "Скрытов"}).json()
    assert rows and not {"phone", "birth_date", "email", "preferences"} & set(rows[0])


def test_card_requires_guests_perm(manager_client, occupancy_client, mgmt_client):
    g = _guest(manager_client)
    assert occupancy_client.get(f"{API}/guests/{g['id']}").status_code == 403
    assert occupancy_client.get(f"{API}/guests", params={"q": "Орлов"}).status_code == 403
    assert mgmt_client.get(f"{API}/guests/{g['id']}").status_code == 200
    assert mgmt_client.put(f"{API}/guests/{g['id']}", json={"last_name": "Новый"}).status_code == 403


def test_preferences_and_special_dates_roundtrip(manager_client):
    g = _guest(manager_client, preferences={"allergy": "орехи", "food": "без глютена"},
               special_dates=[{"date": "2026-10-24", "what": "день рождения"}])
    card = manager_client.get(f"{API}/guests/{g['id']}").json()
    assert card["preferences"]["allergy"] == "орехи"
    assert card["special_dates"] == [{"date": "2026-10-24", "what": "день рождения"}]


def test_guest_update_audited_with_diff(manager_client, db):
    g = _guest(manager_client)
    r = manager_client.put(f"{API}/guests/{g['id']}", json={"last_name": "Орлов", "first_name": "Андрей",
                                                            "level": "vip"})
    assert r.status_code == 200 and r.json()["level"] == "vip"
    row = db.scalars(select(AuditLog).where(AuditLog.action == "stays_guest", AuditLog.target == f"guest:{g['id']}")
                     .order_by(AuditLog.id.desc())).first()
    assert json.loads(row.payload_json)["diff"]["level"] == ["regular", "vip"]
