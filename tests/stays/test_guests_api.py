"""Контракт самостоятельного раздела «Гости» для нестандартных наборов прав."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.identity import AccessGrant, User
from app.modules.people.application import Employee
from tests.stays.conftest import _role_user


@pytest.mark.parametrize(
    ("permissions", "directory", "create"),
    [
        (("stays.guests",), True, False),
        (("stays.edit",), False, True),
        (("stays.guests", "stays.edit"), True, True),
        (("stays.mine_guest_edit",), False, True),
        (("stays.guests", "stays.mine_guest_edit"), True, True),
        ((), False, False),
    ],
)
def test_guests_section_capability_matrix(app_stack, db, permissions, directory, create):
    suffix = uuid.uuid4().hex[:8]
    role = f"gmx_{suffix}"
    db.add_all(AccessGrant(role=role, permission=permission, effect="allow") for permission in permissions)
    db.commit()
    client = _role_user(app_stack, f"guests_{suffix}", role)
    mine_create = "stays.mine_guest_edit" in permissions
    if mine_create:
        user = db.scalar(select(User).where(User.username == f"guests_{suffix}"))
        user.employee_id = db.scalar(select(Employee.id).limit(1))
        db.commit()
        client = _role_user(app_stack, f"guests_{suffix}", role)

    me = client.get("/api/auth/me").json()
    assert ("guests" in {item["id"] for item in me["menu"]}) is (directory or create)
    assert (client.get("/api/stays/guests/list").status_code == 200) is directory
    assert (client.get("/api/stays/guests", params={"q": "нет", "mine": mine_create}).status_code == 200) is (directory or mine_create)
    assert (client.get("/api/stays/fund").status_code == 200) is (directory or create)
    snapshot_status = client.get("/api/stays/fund/snapshot").status_code
    assert (snapshot_status in {200, 422}) is (directory or create)
    assert client.get("/api/stays/fund/snapshot", params={"date": "2000-01-01"}).status_code == 403
    assert client.get("/api/stays/fund/snapshot", params={"version_id": 1}).status_code == 403
    assert client.get("/api/stays/fund/versions").status_code == 403
    response = client.post("/api/stays/guests", json={"last_name": f"Матрица{suffix}"})
    assert (response.status_code == 200) is create


def test_full_directory_with_own_edit_marks_only_owned_card_editable(manager_client, employee_client, db):
    user = db.scalar(select(User).where(User.username == "ivanov"))
    grants = [AccessGrant(user_id=user.id, permission="stays.guests", effect="allow"),
              AccessGrant(user_id=user.id, permission="stays.view", effect="deny"),
              AccessGrant(user_id=user.id, permission="stays.mine", effect="deny")]
    db.add_all(grants)
    db.commit()
    try:
        own = employee_client.post("/api/stays/guests", json={"last_name": "СвойМатрица"}).json()
        foreign = manager_client.post("/api/stays/guests", json={"last_name": "ЧужойМатрица"}).json()
        assert employee_client.get(f"/api/stays/guests/{own['id']}/card").json()["editable"] is True
        assert employee_client.get(f"/api/stays/guests/{foreign['id']}/card").json()["editable"] is False
        assert employee_client.put(f"/api/stays/guests/{own['id']}",
                                   json={"last_name": "СвойМатрица", "note": "своя заметка"}).status_code == 200
        assert employee_client.put(f"/api/stays/guests/{foreign['id']}",
                                   json={"last_name": "ЧужойМатрица", "note": "чужая заметка"}).status_code == 403
    finally:
        for grant in grants:
            db.delete(grant)
        db.commit()


def test_mine_guest_edit_without_employee_has_no_dead_menu_entry(app_stack, db):
    suffix = uuid.uuid4().hex[:8]
    role = f"gmu_{suffix}"
    db.add(AccessGrant(role=role, permission="stays.mine_guest_edit", effect="allow"))
    db.commit()
    client = _role_user(app_stack, f"guest_unlinked_{suffix}", role)
    assert "guests" not in {item["id"] for item in client.get("/api/auth/me").json()["menu"]}
    assert client.post("/api/stays/guests", json={"last_name": "БезСотрудника"}).status_code == 403
