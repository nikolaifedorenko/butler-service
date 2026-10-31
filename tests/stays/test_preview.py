"""Шахматка, задача 9: предпросмотр «что будет, если» (§4.6) — тот же код, откат, та же картина."""
from __future__ import annotations

import pytest
from sqlalchemy import func, select, text

from app.core.audit import AuditLog

from .helpers import API, create_res, make_category, res_body

TABLES = ("stays_reservations", "stays_moves", "stays_assignments", "stays_occupants", "stays_ooo",
          "stays_groups", "stays_companions", "stays_logistics")


def dump(db) -> dict:
    db.expire_all()
    db.rollback()
    out = {t: sorted(map(tuple, db.execute(text(f"SELECT * FROM {t}")).all()), key=repr) for t in TABLES}
    out["audit"] = db.scalar(select(func.count(AuditLog.id)))
    return out


def _put_body(res, **changes):
    return {**{k: res[k] for k in ("number", "check_in", "check_out", "category_id", "early", "late",
                                   "group_id", "note", "declined_butler")},
            "moves": res["moves"], "occupants": res["occupants"], "companions": res["companions"],
            "logistics": res["logistics"], "version": res["version"], **changes}


def _setup(sup, mgr):
    """A 10–14 в первом объекте, B 14–18 в нём же; второй объект свободен."""
    cat = make_category(sup, n_units=2)
    a = create_res(mgr, cat, "2028-03-10", "2028-03-14")
    b = create_res(mgr, cat, "2028-03-14", "2028-03-18")
    return cat, a, b


def _op(name, c, cat, a, b):
    """(метод, путь, тело) операции над A."""
    if name == "move_dates":
        return "PUT", f"{API}/reservations/{a['id']}", _put_body(a, check_out="2028-03-15")
    if name == "pin_other_unit":
        return "PUT", f"{API}/reservations/{a['id']}", _put_body(a, pins={"0": cat["units"][1]["id"]})
    if name == "add_move":
        return "PUT", f"{API}/reservations/{a['id']}", _put_body(
            a, moves=[{"move_date": "2028-03-12", "category_id": cat["id"]}])
    if name == "cancel":
        return "POST", f"{API}/reservations/{a['id']}/status", {"status": "cancelled", "version": a["version"]}
    if name == "no_show":
        return "POST", f"{API}/reservations/{a['id']}/status", {"status": "no_show", "version": a["version"]}
    if name == "join_group":
        gid = c.post(f"{API}/groups", json={"title": "g"}).json()["id"]
        return "PUT", f"{API}/reservations/{a['id']}", _put_body(a, group_id=gid)
    if name == "add_ooo":
        return "POST", f"{API}/holds", {"unit_id": cat["units"][0]["id"], "start": "2028-03-11",
                                        "end": "2028-03-12", "kind": "ooo", "title": "Ремонт"}
    if name == "create":
        return "POST", f"{API}/reservations", res_body(cat, "2028-03-12", "2028-03-16")
    raise AssertionError(name)


@pytest.mark.parametrize("name", ["move_dates", "pin_other_unit", "add_move", "cancel", "no_show",
                                  "join_group", "add_ooo", "create"])
def test_preview_equals_save(manager_role_client, manager_client, db, today, name):
    today("2028-03-10")
    cat, a, b = _setup(manager_role_client, manager_client)
    method, url, body = _op(name, manager_client, cat, a, b)
    before = dump(db)
    pv = manager_client.request(method, url, params={"preview": 1}, json=body)
    assert pv.status_code == 200, pv.text
    assert pv.json()["preview"] is True
    assert dump(db) == before                       # ничего не записано, журнал тоже
    sv = manager_client.request(method, url, json=body)
    assert sv.status_code == 200, sv.text
    assert sv.json()["preview"] is False
    assert pv.json()["diff"] == sv.json()["diff"]
    assert dump(db) != before


def test_preview_shows_other_reservation_shift(manager_role_client, manager_client):
    cat, a, b = _setup(manager_role_client, manager_client)
    # A продлевается на 15-е и закреплена за первым объектом → B вытесняется во второй
    body = _put_body(a, check_out="2028-03-15", pins={"0": cat["units"][0]["id"]})
    pv = manager_client.put(f"{API}/reservations/{a['id']}", params={"preview": 1}, json=body).json()
    moved = {(m["reservation_id"], m["number"], m["from_unit"], m["to_unit"]) for m in pv["diff"]["moved"]}
    assert (b["id"], b["number"], cat["units"][0]["id"], cat["units"][1]["id"]) in moved


def test_preview_reports_new_unassigned_warning(manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=1)
    create_res(manager_client, cat, "2028-04-10", "2028-04-14")
    pv = manager_client.post(f"{API}/reservations", params={"preview": 1},
                             json=res_body(cat, "2028-04-11", "2028-04-13", number="777")).json()
    alloc = [w["kind"] for w in pv["diff"]["warnings_added"] if w["day"] is None]   # без дня — распределение
    assert alloc == ["unassigned"] and pv["diff"]["warnings_removed"] == []


def test_preview_stale_version_409(manager_role_client, manager_client):
    cat, a, b = _setup(manager_role_client, manager_client)
    assert manager_client.put(f"{API}/reservations/{a['id']}", json=_put_body(a, note="x")).status_code == 200
    pv = manager_client.put(f"{API}/reservations/{a['id']}", params={"preview": 1}, json=_put_body(a, note="y"))
    assert pv.status_code == 409 and pv.json()["detail"] == "Бронь изменилась — обновите"


def test_preview_validation_error_same_as_save(manager_role_client, manager_client):
    cat, a, b = _setup(manager_role_client, manager_client)
    body = _put_body(a, check_out=a["check_in"])
    pv = manager_client.put(f"{API}/reservations/{a['id']}", params={"preview": 1}, json=body)
    sv = manager_client.put(f"{API}/reservations/{a['id']}", json=body)
    assert pv.status_code == sv.status_code == 422 and pv.json() == sv.json()
