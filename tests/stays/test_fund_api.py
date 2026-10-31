"""Шахматка, задача 3: справочники фонда, метки, поля, «Сопровождают гостей», настройки."""
from __future__ import annotations

import uuid

from sqlalchemy import select

API = "/api/stays"


def _code() -> str:
    return "C" + uuid.uuid4().hex[:6].upper()


def test_fund_readable_by_supervisor_and_butler(manager_client, employee_client):
    body = manager_client.get(f"{API}/fund").json()
    assert {"labels", "fields", "escorts", "settings"} <= set(body)
    assert not {"categories", "units", "kinds"} & set(body)   # фонд на дату и виды — GET /fund/snapshot
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


def test_settings_bounds_and_nan(manager_role_client):
    base = {"vip_bonus": 1, "vvip_bonus": 2, "daily_limit": 8, "replacement_codes": "ОТ"}
    for bad in ({"daily_limit": 1000}, {"vip_bonus": 1000}, {"daily_limit": "NaN"},
                {"vvip_bonus": "Infinity"}):
        assert manager_role_client.put(f"{API}/settings", json={**base, **bad}).status_code == 422, bad


