"""Шахматка, задача 17: сводная загрузка, «Мои гости», правка своих броней батлером, матрица ролей."""
from __future__ import annotations

from .helpers import API, FundDraft, create_res, kind_id, make_category, make_guest, uniq


def _doc(c, rid):
    return c.get(f"{API}/reservations/{rid}").json()


def _body(res, **ch):
    return {**{k: res[k] for k in ("number", "check_in", "check_out", "category_id", "early", "late", "group_id",
                                   "note", "declined_butler", "label_id", "customer", "paid_category_id", "fields")},
            "moves": res["moves"], "occupants": res["occupants"], "companions": res["companions"],
            "logistics": res["logistics"], "version": res["version"], **ch}


def _group(setup, title: str = "Узел", parent_id: int | None = None) -> int:
    d = FundDraft(setup)
    gid = d.call("POST", "groups", title=title + uniq(), parent_id=parent_id)["id"]
    d.publish()
    return gid


def _occ(c, first: str, last: str, **params) -> dict:
    r = c.get(f"{API}/occupancy", params={"first": first, "last": last, **params})
    assert r.status_code == 200, r.text
    return r.json()


def _by_day(row: dict, days: list[str]) -> dict[str, dict]:
    return dict(zip(days, row["days"], strict=True))


def test_occupancy_grid_counts(manager_role_client, manager_client, occupancy_client):
    gid = _group(manager_role_client)
    cat = make_category(manager_role_client, n_units=3, group_id=gid)
    create_res(manager_client, cat, "2038-01-02", "2038-01-05")
    create_res(manager_client, cat, "2038-01-03", "2038-01-04")
    for c in (manager_client, occupancy_client):
        body = _occ(c, "2038-01-01", "2038-01-05", group_ids=gid)
        [node] = body["nodes"]
        assert node["group_id"] == gid and node["path"][0].startswith("Узел")
        cells = _by_day(node, body["days"])
        assert {x["total"] for x in node["days"]} == {3}
        assert [cells[d]["living"] for d in ("2038-01-01", "2038-01-02", "2038-01-03", "2038-01-04")] == [0, 1, 2, 1]
        assert cells["2038-01-02"]["arrivals"] == 1 and cells["2038-01-04"]["departures"] == 1
        assert cells["2038-01-03"]["pct"] == round(2 / 3, 3)


def test_occupancy_rows(manager_role_client, manager_client):
    """Строки §6.1 на один день: выезд и заезд в тот же объект — по 1 в «Заездах» и «Выездах» и
    1 в «Проживают»; OOO уменьшает знаменатель; блок — в числителе; «Свободно» не меньше 0;
    «Гостей» — по составу; всё в OOO — pct None."""
    gid = _group(manager_role_client)
    cat = make_category(manager_role_client, n_units=3, group_id=gid)
    u1, u2, u3 = (u["id"] for u in cat["units"])
    gs = [make_guest(manager_client)["id"] for _ in range(3)]
    d = "2038-02-10"
    create_res(manager_client, cat, "2038-02-08", d, [(gs[0], "main", None, None)], pins={0: u1})
    create_res(manager_client, cat, d, "2038-02-12", [(gs[1], "main", None, None), (gs[2], "guest", None, None)],
               pins={0: u1})
    for unit, kind in ((u2, "ooo"), (u3, "block")):
        r = manager_client.post(f"{API}/holds", json={"unit_id": unit, "start": d, "end": d, "kind": kind})
        assert r.status_code == 200, r.text
    body = _occ(manager_client, "2038-02-09", "2038-02-11", group_ids=gid)
    cell = _by_day(body["nodes"][0], body["days"])[d]
    assert cell == {"total": 3, "living": 1, "guests": 2, "arrivals": 1, "departures": 1,
                    "free": 0, "ooo": 1, "blocks": 1, "pct": 1.0}       # (1 + 1) / (3 − 1)
    nxt = _by_day(body["nodes"][0], body["days"])["2038-02-11"]
    assert (nxt["living"], nxt["ooo"], nxt["blocks"], nxt["free"], nxt["pct"]) == (1, 0, 0, 2, round(1 / 3, 3))
    # один объект: занят (закреплён) и в OOO — «Свободно» 0, а не −1; весь фонд в OOO — pct None
    solo_g = _group(manager_role_client)
    solo = make_category(manager_role_client, n_units=1, group_id=solo_g)
    create_res(manager_client, solo, d, "2038-02-11", pins={0: solo["units"][0]["id"]})
    assert manager_client.post(f"{API}/holds", json={"unit_id": solo["units"][0]["id"], "start": d, "end": d,
                                                     "kind": "ooo"}).status_code == 200
    body = _occ(manager_client, d, d, group_ids=solo_g)
    cell = body["nodes"][0]["days"][0]
    assert (cell["total"], cell["living"], cell["ooo"], cell["free"], cell["pct"]) == (1, 1, 1, 0, None)


def test_occupancy_by_tree_totals_per_day(manager_role_client, manager_client, today):
    """Узлы и состав — по фонду дня: объект переведён в узел с 15.11 — в узле с 15.11."""
    today("2037-11-01")
    root = _group(manager_role_client, "Корпус")
    block = _group(manager_role_client, "Блок", parent_id=root)
    other = _group(manager_role_client, "Прочее")
    make_category(manager_role_client, n_units=2, group_id=block)
    moved = make_category(manager_role_client, n_units=1, group_id=other)
    m = moved["units"][0]
    create_res(manager_client, moved, "2037-11-10", "2037-11-20", pins={0: m["id"]})
    r = manager_role_client.post(f"{API}/fund/draft", json={"valid_from": "2037-11-15"})
    assert r.status_code == 200, r.text
    rev = r.json()["rev"]
    r = manager_role_client.put(f"{API}/fund/draft/units/{m['id']}", json={
        "rev": rev, "label": m["label"], "category_id": moved["id"], "group_id": block})
    assert r.status_code == 200, r.text
    assert manager_role_client.post(f"{API}/fund/draft/publish", json={"rev": r.json()["rev"]}).status_code == 200
    body = _occ(manager_client, "2037-11-01", "2037-11-30", group_ids=[root, other])
    assert [n["group_id"] for n in body["nodes"]] == [root, other]
    rows = {n["group_id"]: _by_day(n, body["days"]) for n in body["nodes"]}
    assert (rows[root]["2037-11-14"]["total"], rows[root]["2037-11-15"]["total"]) == (2, 3)
    assert (rows[other]["2037-11-14"]["total"], rows[other]["2037-11-15"]["total"]) == (1, 0)
    assert (rows[other]["2037-11-14"]["living"], rows[root]["2037-11-15"]["living"]) == (1, 1)
    sub = _occ(manager_client, "2037-11-01", "2037-11-02", group_ids=block)["nodes"][0]
    assert len(sub["path"]) == 2 and sub["path"][0].startswith("Корпус") and sub["path"][1].startswith("Блок")


def test_occupancy_total_is_sum_of_selected_nodes(manager_role_client, manager_client):
    a, b = _group(manager_role_client), _group(manager_role_client)
    ca = make_category(manager_role_client, n_units=2, group_id=a)
    cb = make_category(manager_role_client, n_units=3, kind="room", group_id=b)
    create_res(manager_client, ca, "2038-03-02", "2038-03-04")
    create_res(manager_client, cb, "2038-03-01", "2038-03-03")
    create_res(manager_client, cb, "2038-03-03", "2038-03-05")
    body = _occ(manager_client, "2038-03-01", "2038-03-05", group_ids=[a, b])
    keys = ("total", "living", "guests", "arrivals", "departures", "free", "ooo", "blocks")
    for i, t in enumerate(body["total"]["days"]):
        assert {k: t[k] for k in keys} == {k: sum(n["days"][i][k] for n in body["nodes"]) for k in keys}
    assert body["total"]["path"] == ["Итого по выбранному"] and body["total"]["days"][2]["living"] == 2
    # фильтры категорий и видов сужают и узлы, и итог
    rooms = _occ(manager_client, "2038-03-01", "2038-03-05", group_ids=[a, b], kind_ids=kind_id("room"))
    assert [n["days"][0]["total"] for n in rooms["nodes"]] == [0, 3] and rooms["total"]["days"][0]["total"] == 3
    # узел и его потомок выбраны вместе — объекты в итоге не удваиваются
    child = _group(manager_role_client, parent_id=a)
    make_category(manager_role_client, n_units=1, group_id=child)
    both = _occ(manager_client, "2038-03-01", "2038-03-01", group_ids=[a, child])
    assert [n["days"][0]["total"] for n in both["nodes"]] == [3, 1] and both["total"]["days"][0]["total"] == 3


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


def test_butler_cannot_change_paid_category(butler_client, own_reservation, manager_role_client):
    rid = own_reservation["mine"]["id"]
    doc = _doc(butler_client, rid)
    other = make_category(manager_role_client)
    r = butler_client.put(f"{API}/reservations/{rid}", json=_body(doc, paid_category_id=other["id"]))
    assert r.status_code == 403
    assert r.json()["detail"] == "Батлер может менять только состав, логистику и сведения о гостях"


def test_butler_cannot_change_paid_category(butler_client, own_reservation, manager_role_client):
    rid = own_reservation["mine"]["id"]
    doc = _doc(butler_client, rid)
    other = make_category(manager_role_client)
    r = butler_client.put(f"{API}/reservations/{rid}", json=_body(doc, paid_category_id=other["id"]))
    assert r.status_code == 403
    assert r.json()["detail"] == "Батлер может менять только состав, логистику и сведения о гостях"
