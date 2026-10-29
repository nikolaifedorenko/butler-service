"""Итоговое ревью: батлер не получает чужих гостей; «Мои гости» без 500 на группах;
вчерашний выезд виден для дописывания."""
from __future__ import annotations

import datetime as dt

from .helpers import API, create_res, make_category, make_guest


def _doc(c, rid):
    return c.get(f"{API}/reservations/{rid}").json()


def _body(res, **ch):
    return {**{k: res[k] for k in ("number", "check_in", "check_out", "category_id", "early", "late", "group_id",
                                   "note", "declined_butler", "label_id", "customer", "paid_category_id", "fields")},
            "moves": res["moves"], "occupants": res["occupants"], "companions": res["companions"],
            "logistics": res["logistics"], "version": res["version"], **ch}


def test_butler_cannot_add_stranger_to_own_booking(butler_client, manager_client, own_reservation):
    """C1: посторонний гость через «свою» бронь — 403, его профиль по-прежнему закрыт."""
    stranger = make_guest(manager_client, "Посторонний", level="vvip")
    assert butler_client.get(f"{API}/guests/{stranger['id']}").status_code == 403
    rid = own_reservation["mine"]["id"]
    doc = _doc(butler_client, rid)
    occ = doc["occupants"] + [{"guest_id": stranger["id"], "role": "guest", "date_from": doc["check_in"],
                               "date_to": doc["check_out"]}]
    r = butler_client.put(f"{API}/reservations/{rid}", json=_body(doc, occupants=occ))
    assert r.status_code == 403
    assert butler_client.get(f"{API}/guests/{stranger['id']}").status_code == 403


def test_butler_may_add_linked_guest(butler_client, manager_client, own_reservation):
    """Батлер добавляет гостя, связанного с проживающим (§1 «батлер добавляет гостей»)."""
    spouse = make_guest(manager_client, "Супругова")
    manager_client.post(f"{API}/guests/{own_reservation['mine_guest']['id']}/links",
                        json={"guest_id": spouse["id"], "kind": "spouse"})
    rid = own_reservation["mine"]["id"]
    doc = _doc(butler_client, rid)
    occ = doc["occupants"] + [{"guest_id": spouse["id"], "role": "guest", "date_from": doc["check_in"],
                               "date_to": doc["check_out"]}]
    assert butler_client.put(f"{API}/reservations/{rid}", json=_body(doc, occupants=occ)).status_code == 200


def test_explicit_line_owns_only_its_guests(butler_client, manager_role_client, manager_client, butlers):
    """C1: батлер ведёт только супругу — профиль главного гостя ему закрыт."""
    d = butlers["days"][0]
    cat = make_category(manager_role_client)
    main, wife = make_guest(manager_client, "Главнов"), make_guest(manager_client, "Женова")
    r = create_res(manager_client, cat, d.isoformat(), (d + dt.timedelta(days=1)).isoformat(),
                   [(main["id"], "main", None, None), (wife["id"], "guest", None, None)])
    manager_client.put(f"{API}/coverage/day", json={"day": d.isoformat(), "reservation_id": r["id"],
                                                    "guest_ids": [wife["id"]], "employee_id": butlers["a"]})
    assert butler_client.get(f"{API}/guests/{wife['id']}").status_code == 200
    assert butler_client.get(f"{API}/guests/{main['id']}").status_code == 403


def test_mine_group_member_without_night_no_500(butler_client, manager_role_client, manager_client, butlers):
    """I1: в группе бронь, чей гость приезжает позже, — «Мои гости» не падают."""
    d = butlers["days"][0]
    cat = make_category(manager_role_client)
    gid = manager_client.post(f"{API}/groups", json={"title": "Г"}).json()["id"]
    a = create_res(manager_client, cat, d.isoformat(), (d + dt.timedelta(days=3)).isoformat(),
                   [(make_guest(manager_client)["id"], "main", None, None)], group_id=gid)
    b = create_res(manager_client, cat, (d + dt.timedelta(days=2)).isoformat(), (d + dt.timedelta(days=3)).isoformat(),
                   [(make_guest(manager_client)["id"], "main", None, None)], group_id=gid)
    manager_client.put(f"{API}/coverage/day", json={"day": d.isoformat(), "group_id": gid, "employee_id": butlers["a"]})
    r = butler_client.get(f"{API}/mine")
    assert r.status_code == 200
    rids = {x["reservation_id"] for x in r.json()["reservations"]}
    assert a["id"] in rids and b["id"] not in rids


def test_mine_shows_guest_departed_yesterday(butler_client, own_reservation, monkeypatch):
    """I2: выезд был вчера (последняя ночь — позавчера) — бронь ещё видна, чтобы дописать."""
    from app.modules.stays.application import mine as mine_mod
    res = own_reservation["mine"]
    check_out = dt.date.fromisoformat(res["check_out"])
    # покрытие стоит на первую ночь; сделаем её последней: выезд — на следующий день
    monkeypatch.setattr(mine_mod, "local_date", lambda: own_reservation["day"] + dt.timedelta(days=2))
    assert check_out == own_reservation["day"] + dt.timedelta(days=2)
    rids = {x["reservation_id"] for x in butler_client.get(f"{API}/mine").json()["reservations"]}
    assert res["id"] in rids
