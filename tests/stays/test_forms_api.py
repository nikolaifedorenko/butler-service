"""Недостающие формы (решение владельца 23.10.2026): совместное проживание одной операцией
с предпросмотром, подходящие брони, справочник фонда для батлера."""
from __future__ import annotations

from .helpers import API, create_res, make_category, make_guest, units_of


def _get(c, rid):
    return c.get(f"{API}/reservations/{rid}").json()


def test_cohabit_candidates(manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=3)
    a = create_res(manager_client, cat, "2039-01-02", "2039-01-06", [(make_guest(manager_client, "Сожитель")["id"], "main", None, None)])
    b = create_res(manager_client, cat, "2039-01-03", "2039-01-05")
    create_res(manager_client, cat, "2039-01-10", "2039-01-12")                 # не пересекается
    got = manager_client.get(f"{API}/reservations/{b['id']}/cohabit").json()
    assert [x["reservation_id"] for x in got] == [a["id"]]
    assert got[0]["main_guest"] == "Сожитель" and got[0]["group_id"] is None


def test_join_and_leave_group_with_preview(manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=3)
    a = create_res(manager_client, cat, "2039-02-02", "2039-02-06")
    b = create_res(manager_client, cat, "2039-02-03", "2039-02-05")
    body = {"reservation_ids": [a["id"], b["id"]]}
    pv = manager_client.post(f"{API}/groups/join", params={"preview": 1}, json=body).json()
    assert _get(manager_client, a["id"])["group_id"] is None                  # предпросмотр ничего не сохранил
    sv = manager_client.post(f"{API}/groups/join", json=body)
    assert sv.status_code == 200 and sv.json()["diff"] == pv["diff"]
    ga, gb = _get(manager_client, a["id"]), _get(manager_client, b["id"])
    assert ga["group_id"] == gb["group_id"] is not None and units_of(ga) == units_of(gb)
    left = manager_client.post(f"{API}/groups/leave", json={"reservation_id": b["id"]})
    assert left.status_code == 200 and _get(manager_client, b["id"])["group_id"] is None


def test_join_group_requires_same_category(manager_role_client, manager_client):
    c1, c2 = make_category(manager_role_client), make_category(manager_role_client)
    a = create_res(manager_client, c1, "2039-03-02", "2039-03-06")
    b = create_res(manager_client, c2, "2039-03-02", "2039-03-06")
    r = manager_client.post(f"{API}/groups/join", json={"reservation_ids": [a["id"], b["id"]]})
    assert r.status_code == 422 and r.json()["detail"] == "Совместное проживание — брони одной категории"


def test_fund_readable_by_butler(butler_client):
    body = butler_client.get(f"{API}/fund").json()
    assert "fields" in body and "staff" not in body
