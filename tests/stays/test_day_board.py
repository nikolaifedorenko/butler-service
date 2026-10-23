"""Шахматка, задача 15: табло дня — итоги, вкладки, статус сопровождения, no-show, уровни ПД."""
from __future__ import annotations

import datetime as dt

from .helpers import API, create_res, make_category, make_guest

DAY = dt.date(2036, 1, 10)


def _iso(d):
    return d.isoformat()


def _setup(sup, mgr, DAY=DAY):
    """В день DAY: заезд в виллу (VIP), выезд, проживающий без батлера, номер без сопровождения."""
    villa = make_category(sup, n_units=3)
    room = make_category(sup, n_units=1, kind="room", escorted=False, weight=1)
    vip = make_guest(mgr, "ТаблоВип", level="vip")
    out_g, stay_g, room_g = make_guest(mgr, "ТаблоВыезд"), make_guest(mgr, "ТаблоЖивёт"), make_guest(mgr, "ТаблоНомер")
    arr = create_res(mgr, villa, _iso(DAY), _iso(DAY + dt.timedelta(days=3)), [(vip["id"], "main", None, None)],
                     early=True, logistics=[{"kind": "transfer", "date": _iso(DAY), "time": "07:40", "description": "SVO"}])
    dep = create_res(mgr, villa, _iso(DAY - dt.timedelta(days=2)), _iso(DAY), [(out_g["id"], "main", None, None)])
    stay = create_res(mgr, villa, _iso(DAY - dt.timedelta(days=1)), _iso(DAY + dt.timedelta(days=2)),
                      [(stay_g["id"], "main", None, None)])
    room_r = create_res(mgr, room, _iso(DAY), _iso(DAY + dt.timedelta(days=1)), [(room_g["id"], "main", None, None)])
    return {"arr": arr, "dep": dep, "stay": stay, "room": room_r}


def _row(rows, rid):
    return next(r for r in rows if r["reservation_id"] == rid)


def test_day_board_totals_and_tabs(manager_role_client, manager_client):
    s = _setup(manager_role_client, manager_client)
    b = manager_client.get(f"{API}/day", params={"date": _iso(DAY)}).json()
    t = b["totals"]
    assert (t["arrivals"], t["departures"], t["in_house"]) == (2, 1, 3)
    assert (t["uncovered"], t["not_required"], t["vip"], t["no_show"]) == (2, 1, 1, 0)
    arr = _row(b["arrivals"], s["arr"]["id"])
    assert arr["time"] == "РЗ" and arr["cover_status"] == "uncovered" and arr["guests"][0]["level"] == "vip"
    assert arr["details"]["logistics"][0]["time"] == "07:40"
    assert _row(b["arrivals"], s["room"]["id"])["cover_status"] == "not_required"
    assert {r["reservation_id"] for r in b["attention"]} == {s["arr"]["id"], s["stay"]["id"]}


def test_day_board_no_show_group(manager_role_client, manager_client, today):
    cat = make_category(manager_role_client)
    d = DAY + dt.timedelta(days=20)
    r = create_res(manager_client, cat, _iso(d), _iso(d + dt.timedelta(days=2)), [(make_guest(manager_client)["id"], "main", None, None)])
    today(_iso(d))
    manager_client.post(f"{API}/reservations/{r['id']}/status", json={"status": "no_show", "version": r["version"]})
    b = manager_client.get(f"{API}/day", params={"date": _iso(d)}).json()
    assert [x["reservation_id"] for x in b["no_show"]] == [r["id"]] and b["totals"]["no_show"] == 1
    assert all(x["reservation_id"] != r["id"] for x in b["arrivals"])


def test_day_board_covered_and_replacement(manager_role_client, manager_client, butlers, db):
    from sqlalchemy import select

    from app.modules.timesheet.application.catalog import TabelDay
    a = butlers["a"]
    day = butlers["days"][11]
    cat = make_category(manager_role_client)
    g = make_guest(manager_client, "ТаблоВедёт")
    r = create_res(manager_client, cat, _iso(day), _iso(day + dt.timedelta(days=1)), [(g["id"], "main", None, None)])
    manager_client.put(f"{API}/coverage/day", json={"day": _iso(day), "reservation_id": r["id"], "employee_id": a})
    row = _row(manager_client.get(f"{API}/day", params={"date": _iso(day)}).json()["in_house"], r["id"])
    assert row["cover_status"] == "covered" and row["covered"][0]["employee_id"] == a
    tabel = db.scalar(select(TabelDay).where(TabelDay.employee_id == a, TabelDay.date == day))
    old = tabel.code
    try:
        tabel.code = "Б"
        db.commit()
        row = _row(manager_client.get(f"{API}/day", params={"date": _iso(day)}).json()["in_house"], r["id"])
        assert row["cover_status"] == "replacement" and isinstance(row["candidates"], list)
    finally:
        tabel.code = old
        db.commit()


def test_day_board_occupancy_level(occupancy_client, manager_role_client, manager_client):
    day = DAY + dt.timedelta(days=40)
    _setup(manager_role_client, manager_client, day)
    r = occupancy_client.get(f"{API}/day", params={"date": _iso(day)})
    assert r.status_code == 200
    for word in ("ТаблоВип", "ТаблоВыезд", "ТаблоЖивёт", "SVO"):
        assert word not in r.text
    row = r.json()["arrivals"][0]
    assert not {"guests", "details", "cover_status", "covered", "candidates", "number"} & set(row)


def test_day_board_filters(manager_role_client, manager_client):
    day = DAY + dt.timedelta(days=60)
    s = _setup(manager_role_client, manager_client, day)
    b = manager_client.get(f"{API}/day", params={"date": _iso(day), "escorted_only": 1, "vip": 1}).json()
    assert [r["reservation_id"] for r in b["arrivals"]] == [s["arr"]["id"]]
    b = manager_client.get(f"{API}/day", params={"date": _iso(day), "q": "табложивёт"}).json()
    assert [r["reservation_id"] for r in b["in_house"]] == [s["stay"]["id"]]


def test_day_board_query_budget(manager_client, big_fund, sql_counter):
    with sql_counter() as c:
        r = manager_client.get(f"{API}/day", params={"date": "2029-06-15"})
    assert r.status_code == 200 and r.json()["totals"]["in_house"] > 20
    assert c["total"] <= 30, sorted(c["by_statement"].items(), key=lambda x: -x[1])[:3]
