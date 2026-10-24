"""Шахматка, задача 3: справочники фонда, метки, поля, «Сопровождают гостей», настройки."""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.audit import AuditLog

API = "/api/stays"


def _code() -> str:
    return "C" + uuid.uuid4().hex[:6].upper()


def _category(c, **kw):
    body = {"code": _code(), "title": "Вилла Garden", "kind": "villa", "escorted": True,
            "weight": 4, **kw}
    r = c.post(f"{API}/categories", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_category_crud_and_audit(manager_role_client, db):
    cat = _category(manager_role_client)
    assert cat["weight"] == 4 and cat["escorted"] is True
    dup = manager_role_client.post(f"{API}/categories", json={
        "code": cat["code"], "title": "Другая", "kind": "villa", "weight": 1})
    assert dup.status_code == 409 and dup.json()["detail"] == "Код категории занят"
    r = manager_role_client.put(f"{API}/categories/{cat['id']}", json={**cat, "weight": 5})
    assert r.status_code == 200 and r.json()["weight"] == 5
    row = db.scalars(select(AuditLog).where(AuditLog.action == "stays_fund",
                                            AuditLog.target == f"category:{cat['id']}")
                     .order_by(AuditLog.id.desc())).first()
    assert row is not None and '"weight": [4.0, 5.0]' in row.payload_json


def test_unknown_kind_refused(manager_role_client):
    r = manager_role_client.post(f"{API}/categories", json={
        "code": _code(), "title": "x", "kind": "castle", "weight": 1})
    assert r.status_code == 422


def test_unit_requires_existing_category(manager_role_client):
    r = manager_role_client.post(f"{API}/units", json={"label": "U" + _code(), "category_id": 999999})
    assert r.status_code == 422 and r.json()["detail"] == "Категория не найдена"


def test_delete_category_with_units_refused(manager_role_client):
    cat = _category(manager_role_client)
    r = manager_role_client.post(f"{API}/units", json={"label": "U" + _code(), "category_id": cat["id"],
                                                        "building": "1", "floor": "2"})
    assert r.status_code == 200, r.text
    r = manager_role_client.delete(f"{API}/categories/{cat['id']}")
    assert r.status_code == 409 and r.json()["detail"] == "В категории есть объекты"


def test_duplicate_unit_label_refused(manager_role_client):
    cat = _category(manager_role_client)
    label = "U" + _code()
    assert manager_role_client.post(f"{API}/units", json={"label": label, "category_id": cat["id"]}).status_code == 200
    r = manager_role_client.post(f"{API}/units", json={"label": label, "category_id": cat["id"]})
    assert r.status_code == 409 and r.json()["detail"] == "Объект с таким обозначением уже есть"


def test_setup_forbidden_for_supervisor(manager_client):
    r = manager_client.post(f"{API}/categories", json={"code": _code(), "title": "x", "kind": "room",
                                                       "weight": 1})
    assert r.status_code == 403


def test_fund_readable_by_supervisor_and_butler(manager_client, employee_client):
    body = manager_client.get(f"{API}/fund").json()
    assert {"categories", "units", "labels", "fields", "escorts", "settings"} <= set(body)
    # батлер (stays.edit_mine) читает справочник ради настраиваемых полей; списка сотрудников нет
    assert "staff" not in employee_client.get(f"{API}/fund").json()


def test_escorts_seed_from_position(manager_role_client, db):
    from app.modules.employees.application.catalog import Employee
    from app.modules.stays.adapters.orm import Escort

    r = manager_role_client.post(f"{API}/escorts/seed", json={})
    assert r.status_code == 200
    ids = set(db.scalars(select(Escort.employee_id)))
    for emp in db.scalars(select(Employee).where(Employee.active.is_(True))):
        assert (emp.id in ids) == ("батлер" in emp.position.lower()), emp.position
    again = manager_role_client.post(f"{API}/escorts/seed", json={"position": "Батлер"}).json()
    assert again["added"] == 0


def test_escort_toggle(manager_role_client, db):
    from app.modules.employees.application.catalog import Employee

    emp = db.scalars(select(Employee)).first()
    r = manager_role_client.put(f"{API}/escorts/{emp.id}", json={"active": False})
    assert r.status_code == 200 and r.json()["active"] is False
    escorts = manager_role_client.get(f"{API}/fund").json()["escorts"]
    assert any(e["employee_id"] == emp.id and e["active"] is False for e in escorts)
    assert manager_role_client.put(f"{API}/escorts/{emp.id}", json={"active": True}).status_code == 200


def test_settings_validation(manager_role_client):
    base = {"vip_bonus": 1, "vvip_bonus": 2, "daily_limit": 8, "replacement_codes": "ОТ,Б"}
    assert manager_role_client.put(f"{API}/settings", json={**base, "daily_limit": 0}).status_code == 422
    assert manager_role_client.put(f"{API}/settings", json={**base, "vip_bonus": -1}).status_code == 422
    r = manager_role_client.put(f"{API}/settings", json={**base, "replacement_codes": " ОТ , Б ,,"})
    assert r.status_code == 200 and r.json()["replacement_codes"] == "ОТ,Б"
    manager_role_client.put(f"{API}/settings", json={**base, "replacement_codes": "ОТ,ДО,Б,ОВ,К"})


def test_choice_field_requires_choices(manager_role_client):
    r = manager_role_client.post(f"{API}/fields", json={
        "target": "guest", "code": "club" + _code().lower(), "title": "Клуб", "kind": "choice",
        "choices": []})
    assert r.status_code == 422 and r.json()["detail"] == "Для списка нужны варианты"


def test_label_crud(manager_role_client):
    r = manager_role_client.post(f"{API}/labels", json={"title": "От руководства " + _code(),
                                                         "color": "#d8833b"})
    assert r.status_code == 200, r.text
    bad = manager_role_client.post(f"{API}/labels", json={"title": "x" + _code(), "color": "red"})
    assert bad.status_code == 422
    assert manager_role_client.delete(f"{API}/labels/{r.json()['id']}").status_code == 200


def test_fund_staff_only_for_setup(manager_role_client, manager_client):
    staff = manager_role_client.get(f"{API}/fund").json()["staff"]
    assert staff and {"id", "name", "position"} <= set(staff[0])
    assert "staff" not in manager_client.get(f"{API}/fund").json()


def test_delete_category_used_in_move_refused(manager_role_client, db):
    from app.modules.stays.adapters.orm import Move, Reservation

    base, target = _category(manager_role_client), _category(manager_role_client)
    import datetime as dt
    r = Reservation(number="M1", check_in=dt.date(2030, 1, 1), check_out=dt.date(2030, 1, 5),
                    category_id=base["id"])
    db.add(r)
    db.flush()
    db.add(Move(reservation_id=r.id, move_date=dt.date(2030, 1, 3), category_id=target["id"]))
    db.commit()
    resp = manager_role_client.delete(f"{API}/categories/{target['id']}")
    assert resp.status_code == 409 and resp.json()["detail"] == "Категория используется в переездах"


def test_settings_bounds_and_nan(manager_role_client):
    base = {"vip_bonus": 1, "vvip_bonus": 2, "daily_limit": 8, "replacement_codes": "ОТ"}
    for bad in ({"daily_limit": 1000}, {"vip_bonus": 1000}, {"daily_limit": "NaN"},
                {"vvip_bonus": "Infinity"}):
        assert manager_role_client.put(f"{API}/settings", json={**base, **bad}).status_code == 422, bad


def test_sort_order_and_weight_bounds(manager_role_client):
    r = manager_role_client.post(f"{API}/categories", json={"code": _code(), "title": "x", "kind": "room",
                                                            "weight": 1, "sort_order": 3_000_000_000})
    assert r.status_code == 422
    r = manager_role_client.post(f"{API}/categories", json={"code": _code(), "title": "x", "kind": "room",
                                                            "weight": "NaN"})
    assert r.status_code == 422

