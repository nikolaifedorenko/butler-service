"""Шахматка, задача 17: сводная загрузка, «Мои гости», правка своих броней батлером, матрица ролей."""
from __future__ import annotations

from .helpers import API, create_res, make_category


def _doc(c, rid):
    return c.get(f"{API}/reservations/{rid}").json()


def _body(res, **ch):
    return {**{k: res[k] for k in ("number", "check_in", "check_out", "category_id", "early", "late", "group_id",
                                   "note", "declined_butler", "label_id", "customer", "purpose", "paid_by", "fields")},
            "moves": res["moves"], "occupants": res["occupants"], "companions": res["companions"],
            "logistics": res["logistics"], "version": res["version"], **ch}


def test_occupancy_grid_counts(manager_role_client, manager_client, occupancy_client):
    cat = make_category(manager_role_client, n_units=3)
    create_res(manager_client, cat, "2038-01-02", "2038-01-05")
    create_res(manager_client, cat, "2038-01-03", "2038-01-04")
    for c in (manager_client, occupancy_client):
        body = c.get(f"{API}/occupancy", params={"first": "2038-01-01", "last": "2038-01-05"}).json()
        row = next(x for x in body["categories"] if x["code"] == cat["code"])
        cells = {x["day"]: x for x in row["cells"]}
        assert row["total"] == 3
        assert [cells[d]["busy"] for d in ("2038-01-01", "2038-01-02", "2038-01-03", "2038-01-04")] == [0, 1, 2, 1]
        assert cells["2038-01-02"]["arrivals"] == 1 and cells["2038-01-04"]["departures"] == 1


def test_butler_edits_own_reservation_logistics(butler_client, own_reservation):
    rid = own_reservation["mine"]["id"]
    doc = _doc(butler_client, rid)
    r = butler_client.put(f"{API}/reservations/{rid}", json=_body(doc, note="батлер дописал",
                          logistics=[{"kind": "car", "date": None, "time": "", "description": "A123BC"}]))
    assert r.status_code == 200, r.text
    assert _doc(butler_client, rid)["note"] == "батлер дописал"


def test_butler_cannot_change_dates(butler_client, own_reservation):
    rid = own_reservation["mine"]["id"]
    doc = _doc(butler_client, rid)
    r = butler_client.put(f"{API}/reservations/{rid}", json=_body(doc, check_out=own_reservation["mine"]["check_in"]))
    assert r.status_code == 403
    assert r.json()["detail"] == "Батлер может менять только состав, логистику и сведения о гостях"


def test_butler_cannot_edit_foreign_reservation(butler_client, own_reservation):
    rid = own_reservation["other"]["id"]
    assert butler_client.get(f"{API}/reservations/{rid}").status_code == 403
    assert butler_client.put(f"{API}/reservations/{rid}", json={"check_in": "2030-01-01", "check_out": "2030-01-02",
                                                                "category_id": 1, "version": 1}).status_code == 403


def test_butler_edits_own_guest_preferences_only(butler_client, own_reservation):
    g = own_reservation["mine_guest"]
    card = butler_client.get(f"{API}/guests/{g['id']}").json()
    body = {k: card[k] for k in ("last_name", "first_name", "middle_name", "email", "level", "note", "fields",
                                 "special_dates", "birth_date")}
    body["phone"] = card["phone"]
    r = butler_client.put(f"{API}/guests/{g['id']}", json={**body, "preferences": {"allergy": "мёд"}})
    assert r.status_code == 200, r.text
    r = butler_client.put(f"{API}/guests/{g['id']}", json={**body, "level": "vvip"})
    assert r.status_code == 403
    other = own_reservation["other_guest"]
    assert butler_client.get(f"{API}/guests/{other['id']}").status_code == 403


def test_mine_lists_only_own(butler_client, own_reservation):
    body = butler_client.get(f"{API}/mine").json()
    rids = {x["reservation_id"] for x in body["reservations"]}
    assert own_reservation["mine"]["id"] in rids and own_reservation["other"]["id"] not in rids
    mine = next(x for x in body["reservations"] if x["reservation_id"] == own_reservation["mine"]["id"])
    assert mine["guests"][0]["name"].startswith("Свойгость") and own_reservation["day"].isoformat() in mine["days"]


def test_butler_sees_yesterday_departed_guest(butler_client, own_reservation, monkeypatch):
    import datetime as dt

    from app.modules.stays.application import mine as mine_mod
    monkeypatch.setattr(mine_mod, "local_date", lambda: own_reservation["day"] + dt.timedelta(days=4))
    rids = {x["reservation_id"] for x in butler_client.get(f"{API}/mine").json()["reservations"]}
    assert own_reservation["mine"]["id"] not in rids        # выезд позавчера — уже не «свой»
    monkeypatch.setattr(mine_mod, "local_date", lambda: own_reservation["day"] + dt.timedelta(days=1))
    rids = {x["reservation_id"] for x in butler_client.get(f"{API}/mine").json()["reservations"]}
    assert own_reservation["mine"]["id"] in rids            # вёл вчера — ещё можно дописать


def test_role_matrix(manager_client, mgmt_client, occupancy_client, butler_client, own_reservation):
    rid = own_reservation["mine"]["id"]
    assert mgmt_client.get(f"{API}/reservations/{rid}/card").status_code == 200
    assert mgmt_client.put(f"{API}/reservations/{rid}", json=_body(_doc(manager_client, rid), note="x")).status_code == 403
    for url in ("/guests?q=а", "/board/butlers?first=2030-01-01&last=2030-01-02", "/mine",
                f"/reservations/{rid}/card", "/coverage/replacements?first=2030-01-01&last=2030-01-02"):
        assert occupancy_client.get(API + url).status_code == 403, url
    assert butler_client.get(f"{API}/board/units", params={"first": "2030-01-01", "last": "2030-01-02"}).status_code == 403


def test_demo_butler_has_tonight(butler_client):
    """Демо: у входа ivanov в «Моих гостях» есть бронь на сегодня (§11)."""
    assert butler_client.get(f"{API}/mine").json()["reservations"]
