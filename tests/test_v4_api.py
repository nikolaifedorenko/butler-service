"""Интеграция движка v4 с прототипом: Табель, УТ (view/close/recalculate), права, аудит, присутствие."""
from __future__ import annotations

import datetime as dt

import pytest

from app.deps import local_date

TODAY = local_date()
PREV_END = TODAY.replace(day=1) - dt.timedelta(days=1)
PREV = PREV_END.replace(day=1)


@pytest.fixture(scope="module")
def admin():
    from fastapi.testclient import TestClient

    from app.main import app
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": "admin", "password": "demo1234"}).status_code == 200
    return c


@pytest.fixture(scope="module")
def emp(admin):
    r = admin.post("/api/employees", json={"full_name": "Закрытов Закрыт Закрытович", "position": "Батлер",
                                           "hired_at": (TODAY - dt.timedelta(days=120)).isoformat(),
                                           "schedule_group": "Смена 1"})
    assert r.status_code == 200, r.text
    e = r.json()
    days = [(PREV + dt.timedelta(days=i)).isoformat() for i in range((PREV_END - PREV).days + 1)]
    assert admin.post("/api/tabel/bulk", json={"employee_ids": [e["id"]], "dates": days, "code": "В"}).status_code == 200
    d1, d2 = PREV + dt.timedelta(days=1), PREV + dt.timedelta(days=2)
    assert admin.put("/api/tabel/cell", json={"employee_id": e["id"], "date": d1.isoformat(),
                                              "code": "Я", "hours": 12}).status_code == 200
    for day, a, b in ((d1, "08:00", "18:00"), (d2, "20:00", "22:00")):
        for kind, t in (("in", a), ("out", b)):
            r = admin.post("/api/punches", json={"kind": kind, "employee_id": e["id"], "ts": f"{day}T{t}"})
            assert r.status_code == 200, r.text
    return {**e, "d1": d1.isoformat(), "d2": d2.isoformat()}


def _row(admin, eid, mode="view", period=PREV):
    data = admin.get("/api/mgmt", params={"year": period.year, "month": period.month, "mode": mode}).json()
    return next(r for r in data["rows"] if r["employee"]["id"] == eid)


def test_view_shows_debt_and_codes(admin, emp):
    row = _row(admin, emp["id"])
    assert row["error"] is None, row["error"]
    assert row["debt"]["total"] == 2 and row["ut"][emp["d2"]] == {"ДЯ": 2}
    preview = _row(admin, emp["id"], "close")
    assert preview["source"] == "preview" and preview["ut"].get(emp["d2"], {}) == {}


def test_close_then_recalculate_last_closed(admin, emp):
    p = {"year": PREV.year, "month": PREV.month, "employee_ids": [emp["id"]]}
    r = admin.post("/api/mgmt/close", json=p).json()
    assert r["errors"] == [] and r["done"][0]["bank_closed"] == 0
    saved = _row(admin, emp["id"], "close")
    assert saved["source"] == "saved" and saved["closed"] and saved["ut"].get(emp["d2"], {}) == {}
    assert saved["debt"]["cut"] == 2
    again = admin.post("/api/mgmt/close", json=p).json()
    assert again["errors"] and "уже закрыт" in again["errors"][0]["error"]
    r = admin.put("/api/tabel/cell", json={"employee_id": emp["id"], "date": emp["d1"], "code": "В"})
    assert r.status_code == 200 and "пересчёт" in r.json()["warning"]
    r = admin.post("/api/mgmt/recalculate", json=p).json()
    assert r["errors"] == []
    saved = _row(admin, emp["id"], "close")
    assert saved["revision"] == 2 and saved["ut"][emp["d2"]] == {"ДЯ": 2} and saved["debt"]["total"] == 0


def test_cannot_close_incomplete_period(admin, emp):
    r = admin.post("/api/mgmt/close", json={"year": TODAY.year, "month": TODAY.month,
                                            "employee_ids": [emp["id"]]}).json()
    assert r["done"] == [] and "не завершён" in r["errors"][0]["error"]


def test_individual_deny_and_group_allow(admin):
    from fastapi.testclient import TestClient

    from app.main import app
    cat = admin.get("/api/access").json()
    gromova = next(u for u in cat["users"] if u["username"] == "gromova")
    ivanov = next(u for u in cat["users"] if u["username"] == "ivanov")
    assert "mgmt.close" in gromova["effective"]
    g = TestClient(app)
    g.post("/api/auth/login", json={"username": "gromova", "password": "demo1234"})
    assert admin.put(f"/api/access/users/{gromova['id']}/grants", json={"grants": {"mgmt.close": "deny"}}).status_code == 200
    assert g.post("/api/mgmt/close", json={"year": PREV.year, "month": PREV.month, "employee_ids": [0]}).status_code == 403
    admin.put(f"/api/access/users/{gromova['id']}/grants", json={"grants": {}})
    i = TestClient(app)
    i.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"})
    assert i.get("/api/tabel", params={"year": TODAY.year, "month": TODAY.month}).status_code == 403
    gid = admin.post("/api/access/groups", json={"name": "Табельщики"}).json()["id"]
    admin.put(f"/api/access/groups/{gid}/grants", json={"grants": {"tabel.view": "allow"}})
    admin.put(f"/api/access/groups/{gid}/members", json={"user_ids": [ivanov["id"]]})
    assert i.get("/api/tabel", params={"year": TODAY.year, "month": TODAY.month}).status_code == 200
    assert "tabel.view" in i.get("/api/auth/me").json()["permissions"]
    admin.put(f"/api/access/users/{ivanov['id']}/grants", json={"grants": {"tabel.view": "deny"}})
    assert i.get("/api/tabel", params={"year": TODAY.year, "month": TODAY.month}).status_code == 403
    admin.put(f"/api/access/users/{ivanov['id']}/grants", json={"grants": {}})
    assert admin.delete(f"/api/access/groups/{gid}").status_code == 200
    assert i.get("/api/tabel", params={"year": TODAY.year, "month": TODAY.month}).status_code == 403
    assert i.get("/api/access").status_code == 403


def test_role_override(admin):
    from fastapi.testclient import TestClient

    from app.main import app
    i = TestClient(app)
    i.post("/api/auth/login", json={"username": "ivanov", "password": "demo1234"})
    assert i.get("/api/presence/board").status_code == 200
    admin.put("/api/access/roles/employee", json={"grants": {"presence.view": "deny"}})
    assert i.get("/api/presence/board").status_code == 403
    admin.put("/api/access/roles/employee", json={"grants": {}})
    assert i.get("/api/presence/board").status_code == 200


def test_audit_tab(admin, emp):
    r = admin.get("/api/audit", params={"action": "period_close"}).json()
    assert r["total"] >= 1 and r["items"][0]["action_title"] == "УТ: закрытие периода"
    assert any(a["action"] == "tabel_cell" for a in r["actions"])
    assert admin.get("/api/audit/csv").status_code == 200
    r = admin.get("/api/audit", params={"q": "Табельщики"}).json()
    assert r["total"] >= 1


def test_modifier_double_overtime(admin, emp):
    day = TODAY - dt.timedelta(days=2)
    if day.month != TODAY.month:
        pytest.skip("начало месяца")
    admin.put("/api/tabel/cell", json={"employee_id": emp["id"], "date": day.isoformat(), "code": "В"})
    for kind, t in (("in", "20:00"), ("out", "22:00")):
        admin.post("/api/punches", json={"kind": kind, "employee_id": emp["id"], "ts": f"{day}T{t}"})
    assert _row(admin, emp["id"], period=TODAY)["ut"][day.isoformat()] == {"ДЯ": 2}
    m = admin.post("/api/engine-settings/modifiers", json={"name": "double_overtime", "value": "1",
                                                           "employee_id": emp["id"], "date": day.isoformat()})
    assert m.status_code == 200, m.text
    assert _row(admin, emp["id"], period=TODAY)["ut"][day.isoformat()] == {"ДЯ 2": 2}
    admin.delete(f"/api/engine-settings/modifiers/{m.json()['id']}")


def test_presence_board_lists_present(admin, emp):
    now = dt.datetime.now().replace(second=0, microsecond=0) - dt.timedelta(minutes=5)
    from app.deps import now_local
    ts = (now_local() - dt.timedelta(minutes=5)).replace(second=0, microsecond=0)
    admin.post("/api/punches", json={"kind": "in", "employee_id": emp["id"], "ts": ts.isoformat(timespec="minutes")})
    board = admin.get("/api/presence/board").json()
    assert any(x["employee"]["id"] == emp["id"] for x in board["present"])
    assert board["counts"]["present"] == len(board["present"]) and now


def test_engine_settings_validation(admin):
    cur = admin.get("/api/engine-settings").json()["active"]["payload"]
    bad = {**cur, "step_minutes": 25}
    r = admin.put("/api/engine-settings", json={"valid_from": "2030-01-01", "payload": bad})
    assert r.status_code == 422 and "V8" in r.json()["detail"]
    r = admin.put("/api/engine-settings", json={"valid_from": "2030-01-15", "payload": cur})
    assert r.status_code == 422
