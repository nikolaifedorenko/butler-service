"""Шахматка, задача 10: шахматка объектов с уровнями видимости (§6.1, §8) и бюджет SQL."""
from __future__ import annotations

from .helpers import API, FundDraft, make_category, uniq

WIN = {"first": "2029-02-01", "last": "2029-02-10"}


def _board(c, demo, **kw):
    return c.get(f"{API}/board/units", params={**WIN, "category_id": demo.cat["id"], **kw})


def test_board_names_level(names_client, demo_small):
    body = _board(names_client, demo_small).json()
    assert body["visibility"] == "names"
    assert len(body["units"]) == 5 and len(body["days"]) == 10
    bars = {b["reservation_id"]: b for b in body["bars"]}
    first = bars[demo_small.res[0]["id"]]
    g0 = demo_small.guests[0]
    assert first["main_guest"] == g0["last_name"]          # у гостя нет имени — инициала нет
    assert first["level"] == "vvip" and first["guests_count"] == 2 and first["number"] == demo_small.res[0]["number"]
    assert "note" not in first and "customer" not in first


def test_board_full_level_has_details(mgmt_client, demo_small):
    assert _board(mgmt_client, demo_small).json()["visibility"] == "full"
    first = next(b for b in _board(mgmt_client, demo_small).json()["bars"]
                 if b["reservation_id"] == demo_small.res[0]["id"])
    assert first["note"].startswith("Заметка") and first["customer"].startswith("Заказчик")


def test_board_main_guest_changes_by_day(manager_client, demo_small):
    rid = demo_small.res[3]["id"]
    b = next(x for x in _board(manager_client, demo_small).json()["bars"] if x["reservation_id"] == rid)
    assert [m["guest"] for m in b["mains"]] == [demo_small.guests[4]["last_name"],
                                               demo_small.guests[5]["last_name"]]


def test_group_shown_in_one_unit(manager_client, demo_small):
    bars = _board(manager_client, demo_small).json()["bars"]
    units = {b["unit_id"] for b in bars if b["reservation_id"] in (demo_small.res[1]["id"], demo_small.res[2]["id"])}
    assert len(units) == 1


def test_board_level_occupancy_no_guest_fields(occupancy_client, demo_small):
    r = _board(occupancy_client, demo_small)
    assert r.status_code == 200
    body = r.text
    for surname in demo_small.surnames:
        assert surname not in body
    bars = r.json()["bars"]
    assert len(bars) == 4
    leaked = {"number", "note", "main_guest", "level", "label", "customer", "mains", "fields"} & set().union(*bars)
    assert not leaked, leaked                       # «label» объекта (обозначение) — не данные гостя
    assert r.json()["warnings"] == []


def test_board_search_and_vip_filters(manager_client, demo_small):
    g = demo_small.guests[3]
    bars = _board(manager_client, demo_small, q=g["last_name"].lower()).json()["bars"]
    assert [b["reservation_id"] for b in bars] == [demo_small.res[2]["id"]]
    vip = _board(manager_client, demo_small, vip=1).json()["bars"]
    assert {b["reservation_id"] for b in vip} == {demo_small.res[0]["id"], demo_small.res[1]["id"]}


def test_board_occupancy_ignores_search(occupancy_client, demo_small):
    g = demo_small.guests[3]
    bars = _board(occupancy_client, demo_small, q=g["last_name"]).json()["bars"]
    assert len(bars) == 4


def test_board_forbidden_without_view(employee_client):
    assert employee_client.get(f"{API}/board/units", params=WIN).status_code == 403


def test_board_window_limit(manager_client):
    r = manager_client.get(f"{API}/board/units", params={"first": "2029-01-01", "last": "2029-06-01"})
    assert r.status_code == 422 and r.json()["detail"] == "Период шахматки — не больше 62 дней"


def test_board_filters_group_branch_and_escorted(manager_role_client, manager_client):
    """Узел дерева фонда — вся его ветка; объект несёт путь узла названиями."""
    d = FundDraft(manager_role_client)
    corp = d.call("POST", "groups", title="Корпус" + uniq())["id"]
    block = d.call("POST", "groups", title="Блок B", parent_id=corp)["id"]
    d.publish()
    in_block = make_category(manager_role_client, n_units=2, group_id=block)
    in_corp = make_category(manager_role_client, n_units=1, group_id=corp, escorted=False)
    make_category(manager_role_client, n_units=1)                  # без узла — вне фильтра
    win = {"first": "2029-06-01", "last": "2029-06-05"}
    branch = manager_client.get(f"{API}/board/units", params={**win, "group_id": corp}).json()["units"]
    assert {u["id"] for u in branch} == {u["id"] for u in in_block["units"] + in_corp["units"]}
    assert {u["group_path"][0] for u in branch} == {corp}
    sub = manager_client.get(f"{API}/board/units", params={**win, "group_id": block}).json()["units"]
    assert {u["id"] for u in sub} == {u["id"] for u in in_block["units"]}
    assert all(u["group"].endswith(" / Блок B") and u["group_path"] == [corp, block] for u in sub)
    esc = manager_client.get(f"{API}/board/units", params={**win, "group_id": corp, "escorted": 1}).json()
    assert {u["id"] for u in esc["units"]} == {u["id"] for u in in_block["units"]}
    assert {b["unit_id"] for b in esc["bars"]} <= {u["id"] for u in esc["units"]}


def test_board_query_budget_440_units(manager_client, big_fund, sql_counter):
    with sql_counter() as c:
        r = manager_client.get(f"{API}/board/units", params=big_fund)
    assert r.status_code == 200
    assert len(r.json()["units"]) >= 440 and len(r.json()["bars"]) >= 300
    assert c["total"] <= 30, sorted(c["by_statement"].items(), key=lambda x: -x[1])[:3]
