"""Вход и права — операции прикладного слоя (ADR-0013, раздел 4)."""
from __future__ import annotations

import pytest
from sqlalchemy import delete, func, select

from app.core import errors
from app.core.audit import AuditLog
from app.core.identity import AccessGroup, LoginAttempt, User
from app.modules.access.application import auth, rights

IP = "203.0.113.77"


@pytest.fixture()
def admin(db):
    from app.core.auth import Principal

    return Principal(db.scalar(select(User).where(User.username == "admin")), None)


@pytest.fixture()
def attempts(db):
    yield
    db.rollback()
    db.execute(delete(LoginAttempt).where(LoginAttempt.key.like(f"ip:{IP}|%")))
    db.commit()


def _failures(app_stack, username: str) -> int:
    with app_stack["SessionLocal"]() as other:        # другая сессия видит только зафиксированное
        return other.scalar(select(func.count()).select_from(LoginAttempt)
                            .where(LoginAttempt.key == auth.attempt_key(IP, username)))


def test_failed_login_is_recorded_although_operation_is_rolled_back(app_stack, db, attempts):
    """Отказ входа откатывает операцию, но неудачная попытка остаётся — иначе лимит не работал бы."""
    with pytest.raises(errors.Unauthorized, match="Неверный логин или пароль") as exc:
        auth.login(db, IP, "admin", "не тот пароль")
    assert exc.value.status_code == 401
    assert _failures(app_stack, "admin") == 1
    with pytest.raises(errors.Unauthorized):
        auth.login(db, IP, "нет-такого-логина", "x")
    assert _failures(app_stack, "нет-такого-логина") == 1


def test_login_limit_and_reset_on_success(app_stack, db, attempts):
    for _ in range(auth.LOGIN_MAX_ATTEMPTS):
        with pytest.raises(errors.Unauthorized):
            auth.login(db, IP, "ivanov", "не тот")
    with pytest.raises(errors.TooManyRequests) as exc:
        auth.login(db, IP, "ivanov", "demo1234")           # верный пароль уже не помогает
    assert exc.value.status_code == 429
    principal, token = auth.login(db, IP, "smirnov", "demo1234")     # другой логин с того же адреса входит
    assert principal.user.username == "smirnov" and token
    assert _failures(app_stack, "ivanov") == auth.LOGIN_MAX_ATTEMPTS


def test_successful_login_is_audited_and_opens_session(db, attempts):
    before = db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "login"))
    principal, token = auth.login(db, IP, " Smirnov ", "demo1234", via_form=True)
    from app.core.sessions import find_session

    row = find_session(db, token)
    assert row is not None and row.user_id == principal.user.id and not row.impersonated
    db.rollback()
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "login")) == before + 1
    last = db.scalar(select(AuditLog).where(AuditLog.action == "login").order_by(AuditLog.id.desc()))
    assert last.target == "user:smirnov (form)"


def test_change_password_refusals_do_not_touch_sessions(db):
    from app.core.auth import Principal

    user = db.scalar(select(User).where(User.username == "smirnov"))
    from app.core.sessions import open_session

    token = open_session(db, user, None)
    db.commit()
    for old, new, text in (("не тот", "NewPass-2026", "Неверный текущий пароль"),
                           ("demo1234", "123", "слишком короткий")):
        with pytest.raises(errors.Rejected, match=text):
            auth.change_password(db, Principal(user, None), old, new)
    db.expire_all()
    from app.core.sessions import find_session

    assert find_session(db, token) is not None, "отказ смены пароля не должен завершать сессии"


def test_stop_impersonation_requires_impersonation(db, admin):
    with pytest.raises(errors.Rejected, match="не в режиме просмотра"):
        auth.stop_impersonation(db, admin)
    with pytest.raises(errors.NotFound, match="Сотрудник не найден"):
        auth.impersonate(db, admin, 10**9)


@pytest.mark.parametrize("call, error, text", [
    (lambda db, p: rights.create_role(db, p, rights.RoleIn(title=" ", rank=30, max_assignable_rank=10)),
     errors.Validation, "Укажите название роли"),
    (lambda db, p: rights.create_role(db, p, rights.RoleIn(title="x", rank=100, max_assignable_rank=10)),
     errors.Validation, "от 1 до 99"),
    (lambda db, p: rights.update_role(db, p, "manager", rights.RoleIn(title="x", rank=30, max_assignable_rank=10)),
     errors.Conflict, "Встроенную роль"),
    (lambda db, p: rights.delete_role(db, p, "нет"), errors.NotFound, "Неизвестная роль"),
    (lambda db, p: rights.create_group(db, p, rights.GroupIn(name="")), errors.Validation, "название группы"),
    (lambda db, p: rights.put_members(db, p, 10**9, rights.MembersIn(user_ids=[])), errors.NotFound, "Группа не найдена"),
    (lambda db, p: rights.put_user_grants(db, p, p.user.id, rights.GrantsIn(grants={"access.manage": "deny"})),
     errors.Conflict, "Нельзя снять с себя"),
    (lambda db, p: rights.put_user_grants(db, p, p.user.id, rights.GrantsIn(grants={"cars.view": "может быть"})),
     errors.Validation, "Неизвестные права или значения"),
])
def test_rights_refusal_is_typed_error(db, admin, call, error, text):
    with pytest.raises(error, match=text):
        call(db, admin)


def test_group_with_bad_members_is_not_changed(app_stack, db, admin):
    """Состав группы заменяется целиком или не меняется: несуществующий пользователь — отказ."""
    name = "Проверка состава группы"
    gid = rights.create_group(db, admin, rights.GroupIn(name=name))
    try:
        ivanov = db.scalar(select(User.id).where(User.username == "ivanov"))
        rights.put_members(db, admin, gid, rights.MembersIn(user_ids=[ivanov]))
        with pytest.raises(errors.Validation, match="Пользователи не найдены"):
            rights.put_members(db, admin, gid, rights.MembersIn(user_ids=[10**9]))
        group = next(g for g in rights.catalog(db)["groups"] if g["id"] == gid)
        assert group["members"] == [ivanov]
    finally:
        rights.delete_group(db, admin, gid)
    with app_stack["SessionLocal"]() as other:
        assert other.scalar(select(func.count()).select_from(AccessGroup).where(AccessGroup.name == name)) == 0
