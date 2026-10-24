"""Шахматка (stays): права по умолчанию и пункты меню из манифеста (§7 спецификации)."""
from __future__ import annotations

from app.core.permissions import role_permissions


def test_stays_permissions_defaults(db):
    sup, emp, man = (role_permissions(db, r) for r in ("supervisor", "employee", "manager"))
    assert {"stays.view", "stays.edit", "stays.assign", "stays.guests"} <= sup
    assert {"stays.edit_mine", "stays.mine"} <= emp
    assert not {"stays.view", "stays.setup", "stays.occupancy"} & emp
    assert {"stays.setup", "stays.export"} <= man
    assert not {"stays.setup", "stays.export"} & sup
    assert "stays.occupancy" not in man          # только своей ролью «Загрузка без гостей»


def test_stays_menu_for_employee(employee_client):
    me = employee_client.get("/api/auth/me").json()
    ids = {m["id"] for m in me["menu"]}
    assert "mystays" in ids and "stays" not in ids



def test_stays_settings_screens_for_manager_only(manager_role_client, manager_client):
    def screens(c):
        return {s["id"] for s in c.get("/api/auth/me").json()["settings_screens"]}
    assert {"stays_fund", "stays_escort", "stays_fields", "stays_labels"} <= screens(manager_role_client)
    assert "stays_fund" not in screens(manager_client)
