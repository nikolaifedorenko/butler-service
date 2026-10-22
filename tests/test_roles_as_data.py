"""Роли как данные (аудит 22.10.2026, ADR-0011, решение владельца: свои роли нужны).

* Иерархия can_manage_user теперь считается по уровням ролей из таблицы roles. На встроенных
  ролях она обязана давать ровно прежние решения — проверка перебором всех сочетаний.
* Своя роль: создание, права через гранты роли, назначение пользователю, иерархия, удаление.
"""
from __future__ import annotations

import itertools

import pytest
from fastapi import HTTPException
from sqlalchemy import select

ROLES = ("admin", "manager", "supervisor", "employee")


def _old_rule(actor: str, target: str | None, new: str | None) -> bool:
    """Прежние правила auth_guards.py (до 22.10.2026), записанные как таблица истинности."""
    if actor == "admin":
        return True
    if actor == "manager":
        return target != "admin" and new != "admin"
    if actor == "supervisor":
        return target in (None, "employee") and new in (None, "employee")
    return False


def test_builtin_hierarchy_matches_previous_rules(db):
    from app.core.auth import Principal
    from app.core.auth_guards import can_manage_user
    from app.core.identity import User

    for actor, target, new in itertools.product(ROLES, (None, *ROLES), (None, *ROLES)):
        principal = Principal(User(username="x", role=actor), None)
        target_user = User(username="y", role=target) if target else None
        try:
            can_manage_user(db, principal, target_user, new)
            allowed = True
        except HTTPException as exc:
            assert exc.status_code == 403, exc.detail
            allowed = False
        assert allowed == _old_rule(actor, target, new), (actor, target, new)


def _user(admin_client, username: str) -> dict:
    return next(e for e in admin_client.get("/api/employees").json() if e.get("username") == username)


def _set_role(client, emp: dict, role: str):
    return client.put(f"/api/employees/{emp['id']}", json={
        "full_name": emp["full_name"], "position": emp["position"],
        "schedule_group": emp["schedule_group"], "hired_at": emp.get("hired_at"), "role": role})


def test_custom_role_lifecycle(admin_client, manager_client, app_stack):
    from tests.conftest import _login

    r = admin_client.post("/api/access/roles", json={
        "title": "Ночной супервайзер", "rank": 59, "max_assignable_rank": 10})
    assert r.status_code == 200, r.text
    code = r.json()["role"]
    emp = _user(admin_client, "volkov")
    try:
        role = next(x for x in admin_client.get("/api/access").json()["roles"] if x["role"] == code)
        assert role["defaults"] == [] and not role["builtin"]
        assert admin_client.put(f"/api/access/roles/{code}",
                                json={"grants": {"night.view": "allow", "night.close": "allow"}}).status_code == 200
        # супервайзер (управляет только уровнем ≤ 10) роль уровня 59 назначить не может
        assert _set_role(manager_client, emp, code).status_code == 403
        assert _set_role(admin_client, emp, code).status_code == 200
        me = _login(app_stack["app"], "volkov").get("/api/auth/me").json()
        assert me["permissions"] == ["night.close", "night.view"]
        assert me["assignable_roles"] == ["employee"]
        assert {"code": code, "title": "Ночной супервайзер"} in me["roles"]
        # и править такую учётку супервайзер больше не может
        assert _set_role(manager_client, emp, "employee").status_code == 403
        assert admin_client.delete(f"/api/access/roles/{code}").status_code == 409   # роль назначена
    finally:
        assert _set_role(admin_client, emp, "employee").status_code == 200
    assert admin_client.delete(f"/api/access/roles/{code}").status_code == 200
    assert code not in {x["role"] for x in admin_client.get("/api/access").json()["roles"]}


@pytest.mark.parametrize("body,status", [
    ({"title": "Админ-2", "rank": 100, "max_assignable_rank": 10}, 422),     # выше 99 — только admin
    ({"title": "Странная", "rank": 20, "max_assignable_rank": 60}, 422),     # назначает выше себя
    ({"title": "Менеджер", "rank": 70, "max_assignable_rank": 10}, 409),     # название занято
])
def test_custom_role_validation(admin_client, body, status):
    assert admin_client.post("/api/access/roles", json=body).status_code == status


def test_builtin_roles_cannot_be_changed_or_deleted(admin_client, manager_client, db):
    from app.core.identity import Role

    assert {r.code for r in db.scalars(select(Role).where(Role.builtin.is_(True)))} == set(ROLES)
    assert admin_client.delete("/api/access/roles/supervisor").status_code == 409
    assert admin_client.put("/api/access/roles/manager/settings", json={
        "title": "Менеджер", "rank": 90, "max_assignable_rank": 90}).status_code == 409
    assert manager_client.post("/api/access/roles", json={
        "title": "Без права", "rank": 20, "max_assignable_rank": -1}).status_code == 403   # access.manage


def test_unknown_role_is_422(db):
    from app.core.auth import Principal
    from app.core.auth_guards import can_manage_user
    from app.core.identity import User

    with pytest.raises(HTTPException) as exc:
        can_manage_user(db, Principal(User(username="x", role="admin"), None), None, "superadmin")
    assert exc.value.status_code == 422
