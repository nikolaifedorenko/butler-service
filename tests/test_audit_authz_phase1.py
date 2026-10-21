"""Аудит 21.10.2026, фаза 1: стражи найденных запуском дыр в правах (AUTHZ-01…04, 10).

Каждый тест — бывший эксперимент аудита (docs/audit/scripts/experiments.py) с
ожиданием исправленного поведения.
"""
from __future__ import annotations

from sqlalchemy import select


def _emp_id(db, username: str) -> int:
    from app.core.identity import User

    return db.scalar(select(User.employee_id).where(User.username == username))


def _employee(client, emp_id: int) -> dict:
    return next(e for e in client.get("/api/employees").json() if e["id"] == emp_id)


def _body(e: dict, **extra) -> dict:
    """Тело PUT /api/employees/{id} из карточки (без role, если не передана явно)."""
    body = {"full_name": e["full_name"], "position": e["position"],
            "schedule_group": e["schedule_group"], "hired_at": e.get("hired_at"),
            "balance_hours": e.get("balance_hours") or 0}
    body.update(extra)
    return body


def test_supervisor_cannot_impersonate_manager(manager_client, db):
    """AUTHZ-01: supervisor (gromova) не входит «как» сотрудник с ролью manager."""
    r = manager_client.post("/api/auth/impersonate", json={"employee_id": _emp_id(db, "smirnov")})
    assert r.status_code == 403, r.text


def test_impersonation_audit_names_who_logged_in(admin_client, db):
    """AUTHZ-01: в журнале действие «как сотрудник» подписано тем, кто вошёл."""
    from app.core.audit import AuditLog

    assert admin_client.post("/api/auth/impersonate",
                             json={"employee_id": _emp_id(db, "petrov")}).status_code == 200
    assert admin_client.post("/api/auth/impersonate/stop").status_code == 200
    row = db.scalars(select(AuditLog).where(AuditLog.action == "impersonate_stop")
                     .order_by(AuditLog.id.desc()).limit(1)).first()
    assert row.actor_name.startswith("admin → как "), row.actor_name


def test_impersonation_ends_when_target_deactivated(admin_client, db):
    """AUTHZ-10: сотрудника уволили во время сессии «как сотрудник» — сессия кончилась."""
    from app.modules.employees.adapters.orm import Employee

    emp_id = _emp_id(db, "orlov")
    assert admin_client.post("/api/auth/impersonate", json={"employee_id": emp_id}).status_code == 200
    emp = db.get(Employee, emp_id)
    emp.active = False
    db.commit()
    try:
        assert admin_client.get("/api/auth/me").status_code == 401
    finally:
        emp.active = True
        db.commit()


def test_punch_for_other_without_permission_is_403(manager_client, db):
    """AUTHZ-02: без punches.punch_for_others отметка «за Сидорова» — 403, а не своя."""
    from app.core.identity import AccessGrant, User

    uid = db.scalar(select(User.id).where(User.username == "gromova"))
    grant = AccessGrant(user_id=uid, permission="punches.punch_for_others", effect="deny")
    db.add(grant)
    db.commit()
    try:
        r = manager_client.post("/api/punches", json={"kind": "auto", "employee_id": _emp_id(db, "sidorov")})
        assert r.status_code == 403, r.text
    finally:
        db.delete(grant)
        db.commit()


def test_put_employee_without_role_keeps_role(admin_client, db):
    """AUTHZ-03: PUT без поля role роль не трогает; смена роли попадает в журнал."""
    from app.core.audit import AuditLog

    # учётка, под которой другие модули не входят заранее: смена роли отзывает сессии
    emp_id = _emp_id(db, "sokolova")
    e = _employee(admin_client, emp_id)
    r = admin_client.put(f"/api/employees/{emp_id}", json=_body(e))
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "employee"

    r = admin_client.put(f"/api/employees/{emp_id}", json=_body(e, role="supervisor"))
    assert r.json()["role"] == "supervisor"
    row = db.scalars(select(AuditLog).where(AuditLog.action == "employee_update")
                     .order_by(AuditLog.id.desc()).limit(1)).first()
    assert '"role": ["employee", "supervisor"]' in row.payload_json
    admin_client.put(f"/api/employees/{emp_id}", json=_body(e, role="employee"))


def test_admin_password_reset_revokes_sessions(admin_client, db, app_stack):
    """AUTHZ-04: новый пароль от руководителя отзывает прежние сессии; короткий — 422."""
    from fastapi.testclient import TestClient

    victim = TestClient(app_stack["app"])
    assert victim.post("/api/auth/login",
                       json={"username": "kuznetsova", "password": "demo1234"}).status_code == 200
    emp_id = _emp_id(db, "kuznetsova")
    e = _employee(admin_client, emp_id)
    assert admin_client.put(f"/api/employees/{emp_id}", json=_body(e, password="short")).status_code == 422
    assert admin_client.put(f"/api/employees/{emp_id}",
                            json=_body(e, password="New-Pass-2026")).status_code == 200
    assert victim.get("/api/auth/me").status_code == 401
    admin_client.put(f"/api/employees/{emp_id}", json=_body(e, password="demo1234"))


def _deny(db, username: str, perm: str):
    from app.core.identity import AccessGrant, User

    g = AccessGrant(user_id=db.scalar(select(User.id).where(User.username == username)),
                    permission=perm, effect="deny")
    db.add(g)
    db.commit()
    return g


def _login(app_stack, username: str):
    from fastapi.testclient import TestClient

    c = TestClient(app_stack["app"])
    assert c.post("/api/auth/login", json={"username": username, "password": "demo1234"}).status_code == 200
    return c


def test_night_walk_requires_night_view(app_stack, db):
    """AUTHZ-06: без night.view нельзя и смотреть, и отмечать обход."""
    from app.modules.night.adapters.orm import NightCheckItem

    item_id = db.scalar(select(NightCheckItem.id).limit(1))
    grant = _deny(db, "volkov", "night.view")
    try:
        c = _login(app_stack, "volkov")
        r = c.put(f"/api/night/items/{item_id}/answer", json={"answer": "ok"})
        assert r.status_code == 403, r.text
    finally:
        db.delete(grant)
        db.commit()


def test_photo_needs_section_permission(app_stack, db):
    """AUTHZ-07: фото возврата кара — только тем, кто видит раздел «Электрокары»."""
    from app.core.media import save_photo

    photo = save_photo(db, kind="car_return", ref_id=1, filename="damage.png",
                       blob=b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, user_id=None, user_name="")
    db.commit()
    c = _login(app_stack, "volkov")
    assert c.get(f"/api/photos/{photo.id}/file").status_code == 200
    grant = _deny(db, "volkov", "cars.view")
    try:
        assert c.get(f"/api/photos/{photo.id}/file").status_code == 403
        assert c.get(f"/api/night/photos/{photo.id}/file").status_code == 403
    finally:
        db.delete(grant)
        db.commit()


def test_bot_api_address_is_not_set_from_ui(admin_client, monkeypatch):
    """SEC-03: адрес Bot API из интерфейса не меняется, а «Проверить» не берёт его из
    запроса — иначе сохранённый токен бота уходил на любой хост."""
    urls: list[str] = []

    def sender(url, payload, files, timeout):
        urls.append(url)
        return {"ok": True, "result": {"username": "bot"}}

    monkeypatch.setattr("app.modules.notify.adapters.transports.telegram.http_sender", sender)
    r = admin_client.put("/api/notify/config", json={"notify_telegram_api": "https://evil.example"})
    assert r.status_code == 400 and "NOTIFY_TELEGRAM_API" in r.json()["detail"], r.text
    r = admin_client.post("/api/notify/telegram/check",
                          json={"token": "1:secret-token", "api": "https://evil.example"})
    assert r.status_code == 200, r.text
    assert urls and all(u.startswith("https://api.telegram.org/") for u in urls), urls


def test_smtp_host_change_requires_password(admin_client):
    """SEC-03: при смене сервера SMTP сохранённый пароль не уходит на новый адрес."""
    put = lambda **kw: admin_client.put("/api/notify/config", json=kw)  # noqa: E731
    assert put(notify_smtp_host="smtp.resort.local", notify_smtp_password="p@ss-1").status_code == 200
    try:
        r = put(notify_smtp_host="smtp.evil.example")
        assert r.status_code == 400 and "пароль" in r.json()["detail"], r.text
        assert put(notify_smtp_host="smtp.evil.example", notify_smtp_password="p@ss-2").status_code == 200
    finally:
        assert put(notify_smtp_host="", notify_smtp_password="clear").status_code == 200


def test_impersonated_punch_is_marked_manual(admin_client, db):
    """В-3: действовать «как сотрудник» можно, но отметка ручная и подписана, кто вошёл."""
    from app.modules.timesheet.adapters.orm import Punch

    emp_id = _emp_id(db, "fedorov")
    assert admin_client.post("/api/auth/impersonate", json={"employee_id": emp_id}).status_code == 200
    r = admin_client.post("/api/punches", json={"kind": "auto"})
    assert r.status_code == 200, r.text
    assert r.json()["punch"]["source"] == "manual"
    p = db.get(Punch, r.json()["punch"]["id"])
    assert p.note.startswith("поставил admin в режиме «как сотрудник»"), p.note


def test_photo_of_closed_night_report_cannot_be_deleted(app_stack, db):
    """В-4: фото закрытого ночного отчёта не удаляется; после переоткрытия — можно."""
    from app.core.identity import User
    from app.core.media import save_photo
    from app.modules.night.adapters.orm import NightAreaSection, NightCheckItem, NightReport

    item = db.scalars(select(NightCheckItem).limit(1)).first()
    rep = db.get(NightReport, db.get(NightAreaSection, item.section_id).report_id)
    status_before = rep.status
    photo = save_photo(db, kind="night_item", ref_id=item.id, filename="proof.png",
                       blob=b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, user_name="Волков",
                       user_id=db.scalar(select(User.id).where(User.username == "volkov")))
    rep.status = "closed"
    db.commit()
    try:
        c = _login(app_stack, "volkov")
        r = c.delete(f"/api/photos/{photo.id}")
        assert r.status_code == 403 and "переоткройте" in r.json()["detail"], r.text
        rep.status = "open"
        db.commit()
        assert c.delete(f"/api/photos/{photo.id}").status_code == 200
    finally:
        rep.status = status_before
        db.commit()
