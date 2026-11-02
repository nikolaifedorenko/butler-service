"""Часть 4, задача 2: батлер на шахматке и табло — уровень «с фамилиями», только чтение, свои брони
выделены и открываются полной карточкой (спека 2026-10-27-stays-butler-mine-design §6, §7)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, select

from .helpers import API, make_category, set_guest
from .test_mine_ownership import _line

DIGITS = "9165550177"


def _board(c, d, days=3):
    r = c.get(f"{API}/board/units", params={"first": d.isoformat(), "last": (d + dt.timedelta(days=days)).isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


def test_butler_sees_units_board_names_level(own_reservation, butler_client):
    d = own_reservation["day"]
    body = _board(butler_client, d)
    assert body["visibility"] == "names"
    bars = {b["reservation_id"]: b for b in body["bars"]}
    mine, other = bars[own_reservation["mine"]["id"]], bars[own_reservation["other"]["id"]]
    assert mine["main_guest"] and other["main_guest"]
    assert not {"customer", "note", "fields", "escort_mode"} & set(other)         # не полный уровень
    assert butler_client.get(f"{API}/day", params={"date": d.isoformat()}).status_code == 200
    assert butler_client.get(f"{API}/board/butlers", params={"first": d.isoformat(), "last": d.isoformat()}).status_code == 200


def test_butler_no_phone_of_foreign_guest(own_reservation, butler_client):
    d = own_reservation["day"]
    set_guest(own_reservation["other_guest"]["id"], phone=DIGITS)
    for path, params in ((f"{API}/board/units", {"first": d.isoformat(), "last": d.isoformat()}),
                         (f"{API}/day", {"date": d.isoformat()}),
                         (f"{API}/reservations/{own_reservation['other']['id']}/card", {})):
        r = butler_client.get(path, params=params)
        assert r.status_code == 200, path
        assert DIGITS not in r.text and "555-01-77" not in r.text, path
    assert butler_client.get(f"{API}/guests/{own_reservation['other_guest']['id']}/card").status_code == 403


def test_butler_own_card_full(own_reservation, butler_client):
    mine, other = own_reservation["mine"], own_reservation["other"]
    own = butler_client.get(f"{API}/reservations/{mine['id']}/card").json()
    assert own["note"] == "старое" and "logistics" in own and "customer" in own          # полный уровень
    foreign = butler_client.get(f"{API}/reservations/{other['id']}/card").json()
    assert "note" not in foreign and "logistics" not in foreign and foreign["occupants"]  # «с фамилиями»


def test_butler_candidates_readable(own_reservation, butler_client):
    d, rid = own_reservation["day"].isoformat(), own_reservation["other"]["id"]
    r = butler_client.get(f"{API}/coverage/candidates", params={"day": d, "reservation_id": rid})
    assert r.status_code == 200 and isinstance(r.json(), list)
    r = butler_client.get(f"{API}/coverage/replacements", params={"first": d, "last": d})
    assert r.status_code == 200


def test_butler_assign_403(own_reservation, butler_client, butlers):
    d, rid = own_reservation["day"].isoformat(), own_reservation["other"]["id"]
    calls = [("PUT", "/coverage/day", {"day": d, "reservation_id": rid, "employee_id": butlers["a"]}),
             ("PUT", "/coverage/days", {"days": [d], "reservation_id": rid, "employee_id": butlers["a"]}),
             ("POST", "/coverage/template", {"reservation_id": rid, "kind": "single", "butlers": [butlers["a"]],
                                              "first": d, "last": d}),
             ("DELETE", "/coverage/1", None),
             ("POST", "/coverage/add-shift", {"employee_id": butlers["a"], "day": d, "shift_type_id": 1})]
    for method, path, body in calls:
        r = butler_client.request(method, f"{API}{path}", json=body)
        assert r.status_code == 403, (path, r.status_code, r.text)


def test_butler_create_reservation_403(own_reservation, butler_client, manager_role_client):
    cat = make_category(manager_role_client, n_units=1)
    d = own_reservation["day"]
    r = butler_client.post(f"{API}/reservations", json={
        "number": "B403", "check_in": d.isoformat(), "check_out": (d + dt.timedelta(days=2)).isoformat(),
        "category_id": cat["id"]})
    assert r.status_code == 403


def test_butler_ooo_block_403(own_reservation, butler_client):
    d = own_reservation["day"].isoformat()
    unit = own_reservation["mine"]["segments"][0]["unit_id"]
    assert butler_client.post(f"{API}/ooo", json={"unit_id": unit, "start": d, "end": d, "reason": "x"}).status_code == 403
    assert butler_client.post(f"{API}/blocks", json={"title": "x", "start": d, "end": d, "nights": []}).status_code == 403


def test_bar_mine_flag_only_own(own_reservation, butler_client, names_client):
    d = own_reservation["day"]
    bars = {b["reservation_id"]: b for b in _board(butler_client, d)["bars"]}
    assert bars[own_reservation["mine"]["id"]]["mine"] is True
    assert bars[own_reservation["other"]["id"]]["mine"] is False
    # без stays.mine признака нет
    plain = _board(names_client, d)["bars"]
    assert plain and all("mine" not in b for b in plain)


def test_units_board_budget_with_mine_flag(big_fund, butler_client, butlers, db, sql_counter):
    from app.modules.stays.adapters.orm import CoverageLine, Reservation

    ids = list(db.scalars(select(Reservation.id).where(Reservation.number.like("BIG%")).limit(25)))
    day = dt.date(2029, 6, 3)
    lines = [_line(butlers["a"], day, rid) for rid in ids]
    try:
        with sql_counter() as c:
            r = butler_client.get(f"{API}/board/units", params=big_fund)
        assert r.status_code == 200
        assert sum(1 for b in r.json()["bars"] if b["mine"]) >= 5
        assert c["total"] <= 30, sorted(c["by_statement"].items(), key=lambda x: -x[1])[:3]
    finally:
        db.execute(delete(CoverageLine).where(CoverageLine.id.in_(lines)))
        db.commit()
