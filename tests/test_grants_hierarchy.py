"""Индивидуальные права — по той же иерархии, что и учётки (рецензия аудита 22.10.2026, топ-5).

put_user_grants требовал только access.manage: менеджер, которому выдали управление
доступом, мог выдать себе любые права поверх роли и снять права администратору.

Что проверяется (менеджер с выданным access.manage):
  * права пользователя старшей роли (admin) менять нельзя — как can_manage_user;
  * выдать право, которого нет у самого, нельзя — ни себе, ни другому;
  * выдать своё право младшему можно;
  * чужая выдача, сделанная администратором, не мешает менеджеру править другие права;
  * то же правило — для прав ролей, прав групп, состава и удаления группы.
"""
from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.core.identity import AccessGrant, User
from app.core.permissions import effective_permissions


def _user(db, username: str) -> User:
    return db.scalar(select(User).where(User.username == username))


@pytest.fixture
def manager(admin_client, manager_role_client, db):
    """Менеджер объекта (smirnov) с выданным администратором access.manage."""
    me = _user(db, "smirnov")
    assert admin_client.put(f"/api/access/users/{me.id}/grants",
                            json={"grants": {"access.manage": "allow"}}).status_code == 200
    touched = [me.id, _user(db, "ivanov").id]
    yield manager_role_client, me
    db.rollback()
    db.execute(delete(AccessGrant).where(AccessGrant.user_id.in_(touched)))
    db.commit()


def _lacking(db, user: User) -> str:
    """Право, которого у пользователя нет (у менеджера — из админских)."""
    have = effective_permissions(db, user.id, user.role)
    return sorted(k for k in effective_permissions(db, _user(db, "admin").id, "admin") if k not in have)[0]


def test_cannot_touch_senior_role(manager, db):
    client, _ = manager
    admin = _user(db, "admin")
    r = client.put(f"/api/access/users/{admin.id}/grants", json={"grants": {"night.view": "deny"}})
    assert r.status_code == 403, r.text
    assert not db.scalars(select(AccessGrant).where(AccessGrant.user_id == admin.id)).all()


def test_cannot_grant_what_you_lack(manager, db):
    client, me = manager
    missing = _lacking(db, me)
    ivanov = _user(db, "ivanov")
    for uid in (me.id, ivanov.id):
        r = client.put(f"/api/access/users/{uid}/grants",
                       json={"grants": {"access.manage": "allow", missing: "allow"} if uid == me.id
                             else {missing: "allow"}})
        assert r.status_code == 403 and missing in r.json()["detail"], r.text
    assert missing not in effective_permissions(db, me.id, me.role)


def test_can_grant_own_permission_to_junior(manager, db):
    client, me = manager
    ivanov = _user(db, "ivanov")
    own = sorted(effective_permissions(db, me.id, me.role)
                 - effective_permissions(db, ivanov.id, ivanov.role))[0]
    r = client.put(f"/api/access/users/{ivanov.id}/grants", json={"grants": {own: "allow"}})
    assert r.status_code == 200, r.text
    assert own in effective_permissions(db, ivanov.id, ivanov.role)


def test_admin_grant_survives_manager_edit(manager, admin_client, db):
    client, me = manager
    ivanov = _user(db, "ivanov")
    missing = _lacking(db, me)
    assert admin_client.put(f"/api/access/users/{ivanov.id}/grants",
                            json={"grants": {missing: "allow"}}).status_code == 200
    r = client.put(f"/api/access/users/{ivanov.id}/grants",
                   json={"grants": {missing: "allow", "night.view": "deny"}})
    assert r.status_code == 200, r.text
    # снять чужую выдачу можно — это не расширение прав
    r = client.put(f"/api/access/users/{ivanov.id}/grants", json={"grants": {}})
    assert r.status_code == 200, r.text


# ═══════════════ роли и группы: то же правило, иначе обход через соседнюю вкладку ═══════════════

@pytest.fixture
def group(admin_client, db):
    """Группа доступа, созданная администратором; удаляется за тестом."""
    r = admin_client.post("/api/access/groups", json={"name": "Тест иерархии прав"})
    assert r.status_code == 200, r.text
    gid = r.json()["id"]
    yield gid
    admin_client.delete(f"/api/access/groups/{gid}")


def _own(db, me: User) -> str:
    """Своё право менеджера, которого нет у сотрудника по умолчанию."""
    ivanov = _user(db, "ivanov")
    return sorted(effective_permissions(db, me.id, me.role)
                  - effective_permissions(db, ivanov.id, ivanov.role))[0]


def test_role_grants_follow_hierarchy(manager, db):
    client, me = manager
    missing = _lacking(db, me)
    saved = [(g.permission, g.effect) for g in db.scalars(select(AccessGrant)
                                                           .where(AccessGrant.role == "employee"))]
    try:
        r = client.put("/api/access/roles/admin", json={"grants": {"night.view": "deny"}})
        assert r.status_code == 403, r.text                       # старшая роль
        r = client.put(f"/api/access/roles/{me.role}", json={"grants": {missing: "allow"}})
        assert r.status_code == 403 and missing in r.json()["detail"], r.text
        r = client.put("/api/access/roles/employee",
                       json={"grants": dict(saved) | {_own(db, me): "allow"}})
        assert r.status_code == 200, r.text
    finally:
        db.rollback()
        db.execute(delete(AccessGrant).where(AccessGrant.role == "employee"))
        db.add_all([AccessGrant(role="employee", permission=k, effect=v) for k, v in saved])
        db.commit()


def test_group_grants_follow_hierarchy(manager, admin_client, group, db):
    client, me = manager
    ivanov, admin = _user(db, "ivanov"), _user(db, "admin")
    assert admin_client.put(f"/api/access/groups/{group}/members",
                            json={"user_ids": [ivanov.id]}).status_code == 200
    missing = _lacking(db, me)
    r = client.put(f"/api/access/groups/{group}/grants", json={"grants": {missing: "allow"}})
    assert r.status_code == 403 and missing in r.json()["detail"], r.text
    r = client.put(f"/api/access/groups/{group}/grants", json={"grants": {_own(db, me): "allow"}})
    assert r.status_code == 200, r.text
    # в группе администратор — её права менеджеру не по рангу
    assert admin_client.put(f"/api/access/groups/{group}/members",
                            json={"user_ids": [ivanov.id, admin.id]}).status_code == 200
    r = client.put(f"/api/access/groups/{group}/grants", json={"grants": {"night.view": "deny"}})
    assert r.status_code == 403, r.text


def test_group_members_follow_hierarchy(manager, admin_client, group, db):
    client, me = manager
    ivanov, admin = _user(db, "ivanov"), _user(db, "admin")
    missing = _lacking(db, me)
    url = f"/api/access/groups/{group}/members"

    # вход в группу с чужим allow — выдача права, которого у менеджера нет
    assert admin_client.put(f"/api/access/groups/{group}/grants",
                            json={"grants": {missing: "allow"}}).status_code == 200
    for ids in ([me.id], [ivanov.id]):
        r = client.put(url, json={"user_ids": ids})
        assert r.status_code == 403 and missing in r.json()["detail"], r.text

    # выход из группы с чужим deny — тоже расширение
    assert admin_client.put(f"/api/access/groups/{group}/grants",
                            json={"grants": {missing: "deny"}}).status_code == 200
    assert admin_client.put(url, json={"user_ids": [ivanov.id]}).status_code == 200
    r = client.put(url, json={"user_ids": []})
    assert r.status_code == 403 and missing in r.json()["detail"], r.text

    # своё право — можно; администратора в группу менеджер не добавит
    assert admin_client.put(f"/api/access/groups/{group}/grants",
                            json={"grants": {_own(db, me): "allow"}}).status_code == 200
    assert client.put(url, json={"user_ids": []}).status_code == 200
    assert client.put(url, json={"user_ids": [ivanov.id]}).status_code == 200
    r = client.put(url, json={"user_ids": [ivanov.id, admin.id]})
    assert r.status_code == 403, r.text


def test_delete_group_follows_hierarchy(manager, admin_client, group, db):
    """Удаление группы — тоже смена прав участников: они теряют её allow и её deny.
    Снятие чужого deny — расширение; участник старшей роли — не по рангу."""
    client, me = manager
    ivanov, admin = _user(db, "ivanov"), _user(db, "admin")
    missing = _lacking(db, me)
    url = f"/api/access/groups/{group}"

    assert admin_client.put(f"{url}/members", json={"user_ids": [ivanov.id]}).status_code == 200
    assert admin_client.put(f"{url}/grants", json={"grants": {missing: "deny"}}).status_code == 200
    r = client.delete(url)
    assert r.status_code == 403 and missing in r.json()["detail"], r.text

    assert admin_client.put(f"{url}/grants", json={"grants": {_own(db, me): "deny"}}).status_code == 200
    assert admin_client.put(f"{url}/members",
                            json={"user_ids": [ivanov.id, admin.id]}).status_code == 200
    assert client.delete(url).status_code == 403                  # в группе администратор

    assert admin_client.put(f"{url}/members", json={"user_ids": [ivanov.id]}).status_code == 200
    assert client.delete(url).status_code == 200                  # своё право, младший участник
