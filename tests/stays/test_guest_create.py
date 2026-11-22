"""Создание гостя батлером (раздел «Гости», ревью UI 22.11.2026): POST /api/stays/guests
доступен и с правом stays.mine_guest_edit; VIP-код и «особый гость» — только менеджеры
(stays.edit); созданный батлером гость сразу «свой» — created_by — сотрудник батлера."""
from __future__ import annotations

from sqlalchemy import select

from app.modules.guests.application.catalog import Guest
from app.modules.people.application import Employee
from app.modules.stays.application import mine

from .helpers import API, uniq


def _new(**body) -> dict:
    return {"last_name": "Заведён" + uniq(), "first_name": "Иван", "phone": "", "email": "",
            "birth_date": None, "gender": "", "special": False, "vip_code_id": None,
            "preferences": {}, "special_dates": [], "fields": {}, "note": "", **body}


def _ivanov_id(db) -> int:
    return next(e.id for e in db.scalars(select(Employee)) if "Иванов" in e.display_name)


def test_manager_creates_guest_with_vip_and_special(manager_client, db):
    r = manager_client.post(f"{API}/guests", json=_new(special=True))
    assert r.status_code == 200, r.text
    assert r.json()["special"] is True
    # заведённый менеджером гость ничьей «свой» не становится
    assert db.get(Guest, r.json()["id"]).created_by_employee_id is None


def test_butler_creates_own_guest(employee_client, db):
    r = employee_client.post(f"{API}/guests", json=_new(phone="+79165550199"))
    assert r.status_code == 200, r.text
    g = db.get(Guest, r.json()["id"])
    assert g.created_by_employee_id == _ivanov_id(db)
    assert mine.owns_guest(db, g.created_by_employee_id, g.id)


def test_butler_create_rejects_vip_and_special(employee_client):
    r = employee_client.post(f"{API}/guests", json=_new(special=True, vip_code_id=1))
    assert r.status_code == 403, r.text


def test_guest_create_requires_login(app_stack):
    from fastapi.testclient import TestClient

    assert TestClient(app_stack["app"]).post(f"{API}/guests", json=_new()).status_code == 401
