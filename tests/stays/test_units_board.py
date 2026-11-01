"""Шахматка, задача 10: шахматка объектов с уровнями видимости (§6.1, §8) и бюджет SQL."""
from __future__ import annotations

import datetime as dt

from app.modules.stays.domain.halfday import AM, PM, pos

from .helpers import API, FundDraft, create_res, make_category, uniq

WIN = {"first": "2029-02-01", "last": "2029-02-10"}


def _board(c, demo, **kw):
    return c.get(f"{API}/board/units", params={**WIN, "category_ids": demo.cat["id"], **kw})


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
    villas = d.call("POST", "groups", title="Виллы" + uniq())["id"]
    d.publish()
    in_block = make_category(manager_role_client, n_units=2, group_id=block)
    in_corp = make_category(manager_role_client, n_units=1, group_id=corp, escorted=False)
    in_villas = make_category(manager_role_client, n_units=1, group_id=villas)
    make_category(manager_role_client, n_units=1)                  # без узла — вне фильтра
    win = {"first": "2029-06-01", "last": "2029-06-05"}
    branch = manager_client.get(f"{API}/board/units", params={**win, "group_ids": corp}).json()["units"]
    assert {u["unit_id"] for u in branch} == {u["id"] for u in in_block["units"] + in_corp["units"]}
    assert {u["group_path"][0] for u in branch} == {corp}
    sub = manager_client.get(f"{API}/board/units", params={**win, "group_ids": block}).json()["units"]
    assert {u["unit_id"] for u in sub} == {u["id"] for u in in_block["units"]}
    assert all(u["group"].endswith(" / Блок B") and u["group_path"] == [corp, block] for u in sub)
    esc = manager_client.get(f"{API}/board/units", params={**win, "group_ids": corp, "escorted": 1}).json()
    assert {u["unit_id"] for u in esc["units"]} == {u["id"] for u in in_block["units"]}
    assert {b["unit_id"] for b in esc["bars"]} <= {u["unit_id"] for u in esc["units"]}
    both = manager_client.get(f"{API}/board/units", params={**win, "group_ids": [block, villas]}).json()["units"]
    assert {u["unit_id"] for u in both} == {u["id"] for u in in_block["units"] + in_villas["units"]}   # узлы — «или»


def test_board_query_budget_440_units(manager_client, big_fund, sql_counter):
    with sql_counter() as c:
        r = manager_client.get(f"{API}/board/units", params=big_fund)
    assert r.status_code == 200
    assert len(r.json()["units"]) >= 440 and len(r.json()["bars"]) >= 300
    assert c["total"] <= 30, sorted(c["by_statement"].items(), key=lambda x: -x[1])[:3]


# ── часть 2, задача 6: OOO, блоки и овербукинг на шахматке ──

def _ooo(c, unit_id, start, end, reason="Ремонт", **kw):
    r = c.post(f"{API}/ooo", json={"unit_id": unit_id, "start": start, "end": end, "reason": reason, **kw})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def _mkblock(c, title, start, end, grid):
    r = c.post(f"{API}/blocks", json={"title": title, "start": start, "end": end, "grid": grid})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def _brd(c, cat, first, last):
    r = c.get(f"{API}/board/units", params={"first": first, "last": last, "category_ids": cat["id"]})
    assert r.status_code == 200, r.text
    return r.json()


def test_ooo_bar_halves(manager_role_client, manager_client, occupancy_client):
    """OOO — полоса по половинкам с причиной: по умолчанию с вечера «с» до утра «по»; «с утра» и
    «до вечера» — сутки целиком. Причина без персональных данных — видна и уровню «занятость»."""
    cat = make_category(manager_role_client, n_units=2)
    u1, u2 = (u["id"] for u in cat["units"])
    a = _ooo(manager_client, u1, "2046-03-10", "2046-03-12", "Покраска")
    b = _ooo(manager_client, u2, "2046-03-10", "2046-03-12", "Сутки", start_half="AM", end_half="PM")
    for c in (manager_client, occupancy_client):
        holds = {h["id"]: h for h in _brd(c, cat, "2046-03-08", "2046-03-14")["holds"]}
        d = dt.date(2046, 3, 10)
        assert (holds[a["id"]]["start_pos"], holds[a["id"]]["end_pos"]) == (pos(d, PM), pos(dt.date(2046, 3, 12), AM))
        assert (holds[b["id"]]["start_pos"], holds[b["id"]]["end_pos"]) == (pos(d, AM), pos(dt.date(2046, 3, 12), PM))
        assert (holds[a["id"]]["title"], holds[b["id"]]["title"]) == ("Покраска", "Сутки")
        assert holds[a["id"]]["kind"] == "ooo" and holds[a["id"]]["start_half"] == "PM"


def test_block_slot_bars_merged(manager_role_client, manager_client, occupancy_client):
    """Слот блока — полоса: соседние ночи одного слота в одном объекте склеены; слот 2 есть только
    в ночах с остатком 2. Название блока видно всем уровням; полоса не бронь (без reservation_id)."""
    cat = make_category(manager_role_client, n_units=3)
    grid = {cat["id"]: {"2046-04-10": 2, "2046-04-11": 2, "2046-04-12": 1, "2046-04-13": 1}}
    blk = _mkblock(manager_client, "Конгресс", "2046-04-10", "2046-04-14", grid)
    for c in (manager_client, occupancy_client):
        data = _brd(c, cat, "2046-04-08", "2046-04-16")
        bars = sorted(data["blocks"], key=lambda x: (x["slot"], x["start"]))
        assert [(x["slot"], x["start"], x["end"]) for x in bars] == [(1, "2046-04-10", "2046-04-14"),
                                                                     (2, "2046-04-10", "2046-04-12")]
        assert all(x["block_id"] == blk["id"] and x["title"] == "Конгресс" and x["category_id"] == cat["id"]
                   and x["unit_id"] in {u["id"] for u in cat["units"]} and "reservation_id" not in x for x in bars)
        assert bars[0]["unit_id"] != bars[1]["unit_id"]
        assert (bars[0]["start_pos"], bars[0]["end_pos"]) == (pos(dt.date(2046, 4, 10), PM), pos(dt.date(2046, 4, 14), AM))


def test_block_bar_split_when_slot_changes_unit(manager_role_client, manager_client):
    """Слот, которому в середине пришлось сменить объект (OOO на ночь 11-го), — две полосы встык."""
    cat = make_category(manager_role_client, n_units=2)
    u1, u2 = (u["id"] for u in cat["units"])
    _mkblock(manager_client, "Сдвиг", "2046-05-10", "2046-05-13", {cat["id"]: {"2046-05-10": 1, "2046-05-11": 1,
                                                                              "2046-05-12": 1}})
    first = sorted(_brd(manager_client, cat, "2046-05-08", "2046-05-16")["blocks"], key=lambda x: x["start"])
    assert len(first) == 1 and first[0]["unit_id"] in (u1, u2)
    _ooo(manager_client, first[0]["unit_id"], "2046-05-11", "2046-05-12")
    bars = sorted(_brd(manager_client, cat, "2046-05-08", "2046-05-16")["blocks"], key=lambda x: x["start"])
    assert [(x["start"], x["end"]) for x in bars] == [("2046-05-10", "2046-05-11"), ("2046-05-11", "2046-05-13")]
    assert len({x["unit_id"] for x in bars}) == 2 and {x["slot"] for x in bars} == {1}


def test_overbooked_in_unassigned(manager_role_client, manager_client, occupancy_client):
    """Бронь без объекта (овербукинг) — в «Не распределено» с признаком overbooked; обычная — без."""
    cat = make_category(manager_role_client, n_units=1)
    u1 = cat["units"][0]["id"]
    ok = create_res(manager_client, cat, "2046-06-01", "2046-06-03", pins={0: u1})
    _ooo(manager_client, u1, "2046-06-05", "2046-06-08")
    over = create_res(manager_client, cat, "2046-06-04", "2046-06-07")
    for c in (manager_client, occupancy_client):
        bars = {b["reservation_id"]: b for b in _brd(c, cat, "2046-06-01", "2046-06-10")["bars"]}
        assert bars[over["id"]]["unit_id"] is None and bars[over["id"]]["overbooked"] is True
        assert bars[ok["id"]]["unit_id"] == u1 and bars[ok["id"]]["overbooked"] is False


def test_board_budget_with_ooo_and_blocks(manager_role_client, manager_client, big_fund, sql_counter):
    """440 объектов × 31 день с OOO и блоком — не больше 30 запросов (часть 1)."""
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modules.stays.adapters.orm import CategoryState

    with SessionLocal() as s:
        rows = list(s.execute(select(CategoryState.category_id, CategoryState.code)
                              .where(CategoryState.code.in_(("BIGDLX", "BIGSTE"))).distinct()))
    cats = {code: cid for cid, code in rows}
    units = manager_client.get(f"{API}/board/units", params=big_fund).json()["units"]
    victims = [u["unit_id"] for u in units][:5]
    oo = [_ooo(manager_client, uid, "2029-06-10", "2029-06-12") for uid in victims]
    blk = _mkblock(manager_client, "Бюджет", "2029-06-05", "2029-06-20",
                   {cats["BIGDLX"]: {f"2029-06-{d:02d}": 3 for d in range(5, 20)}})
    try:
        with sql_counter() as c:
            r = manager_client.get(f"{API}/board/units", params=big_fund)
        assert r.status_code == 200
        body = r.json()
        assert body["holds"] and body["blocks"]
        assert c["total"] <= 30, sorted(c["by_statement"].items(), key=lambda x: -x[1])[:3]
    finally:
        manager_client.delete(f"{API}/blocks/{blk['id']}", params={"version": 1})
        for o in oo:
            manager_client.delete(f"{API}/ooo/{o['id']}", params={"version": 1})
