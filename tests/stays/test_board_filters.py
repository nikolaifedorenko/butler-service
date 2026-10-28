"""Фильтры видов по дереву, категориям, видам и флагам (спецификация stays-fund-versions §6, §7):
«или» внутри измерения, «и» между ними, флаги — все; каждый день — по фонду этого дня; дни
«нет в фонде» / «вне фильтра», смена обозначения и категории, загрузка строки; табло дня;
бюджет SQL месяца; прежние параметры — 422; поиск и VIP для уровня occupancy не применяются."""
from __future__ import annotations

from .helpers import API, FundDraft, create_res, make_category, make_guest, uniq

MONTH = {"first": "2036-11-01", "last": "2036-11-30"}


def _version(setup, valid_from: str, *edits) -> None:
    """Опубликовать версию фонда с даты: edits — (метод, путь, тело) правок черновика."""
    r = setup.post(f"{API}/fund/draft", json={"valid_from": valid_from})
    assert r.status_code == 200, r.text
    rev = r.json()["rev"]
    for method, path, body in edits:
        if method == "DELETE":
            resp = setup.delete(f"{API}/fund/draft/{path}", params={"rev": rev})
        else:
            resp = setup.request(method, f"{API}/fund/draft/{path}", json={"rev": rev, **body})
        assert resp.status_code == 200, resp.text
        rev = resp.json()["rev"]
    resp = setup.post(f"{API}/fund/draft/publish", json={"rev": rev})
    assert resp.status_code == 200, resp.text


def _groups(setup, *titles: str) -> list[int]:
    d = FundDraft(setup)
    ids = [d.call("POST", "groups", title=t + uniq())["id"] for t in titles]
    d.publish()
    return ids


def _flag(setup) -> int:
    r = setup.post(f"{API}/fund/flags", json={"title": "Флаг" + uniq()})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _set_flag(setup, flag: int, unit_ids: list[int]) -> None:
    d = FundDraft(setup)
    d.call("PUT", "flags", flag_id=flag, unit_ids=unit_ids, value=True)
    d.publish()


def _ids(cat: dict, *idx: int) -> set[int]:
    return {cat["units"][i]["id"] for i in idx}


def _board(c, **params) -> dict:
    r = c.get(f"{API}/board/units", params={**MONTH, **params})
    assert r.status_code == 200, r.text
    return r.json()


def _rows(c, **params) -> dict[int, dict]:
    return {u["unit_id"]: u for u in _board(c, **params)["units"]}


def test_or_within_dimension_and_between(manager_role_client, manager_client):
    corp, villas = _groups(manager_role_client, "Корпус", "Виллы")
    rooms = make_category(manager_role_client, n_units=2, kind="room", group_id=corp)
    vil = make_category(manager_role_client, n_units=2, kind="villa", group_id=villas)
    sea = _flag(manager_role_client)
    _set_flag(manager_role_client, sea, [vil["units"][0]["id"], rooms["units"][0]["id"]])
    # узлы — «или»: «Корпус» + «Виллы» → оба
    assert set(_rows(manager_client, group_ids=[corp, villas])) == _ids(rooms, 0, 1) | _ids(vil, 0, 1)
    # «Виллы» и флаг → только виллы с флагом
    assert set(_rows(manager_client, group_ids=[villas], flag_ids=[sea])) == _ids(vil, 0)
    # категории — «или», вид — «и» с узлами
    assert set(_rows(manager_client, category_ids=[rooms["id"], vil["id"]])) == _ids(rooms, 0, 1) | _ids(vil, 0, 1)
    assert set(_rows(manager_client, group_ids=[corp, villas], kinds=["villa"])) == _ids(vil, 0, 1)
    assert set(_rows(manager_client, group_ids=[corp], kinds=["villa", "room"])) == _ids(rooms, 0, 1)
    row = _rows(manager_client, group_ids=[villas])[vil["units"][0]["id"]]
    assert row["flags"] == [sea] and row["group_path"] == [villas] and row["off"] == []
    assert row["category_id"] == vil["id"] and row["label"] == vil["units"][0]["label"]


def test_flags_are_and(manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=3)
    f1, f2 = _flag(manager_role_client), _flag(manager_role_client)
    _set_flag(manager_role_client, f1, [u["id"] for u in cat["units"][:2]])
    _set_flag(manager_role_client, f2, [cat["units"][0]["id"]])
    assert set(_rows(manager_client, category_ids=[cat["id"]], flag_ids=[f1, f2])) == _ids(cat, 0)
    assert set(_rows(manager_client, category_ids=[cat["id"]], flag_ids=[f1])) == _ids(cat, 0, 1)


def test_flag_filter_respects_version_day(manager_role_client, manager_client, today):
    """Флаг с 15.11: объект в шахматке есть, полоса и «занято» до 15.11 не скрыты — строка просто
    вне фильтра в дни до версии; «Загрузка» считает объект в фильтре только с 15.11."""
    today("2036-11-01")
    cat = make_category(manager_role_client, n_units=1)
    uid = cat["units"][0]["id"]
    sea = _flag(manager_role_client)
    r = create_res(manager_client, cat, "2036-11-05", "2036-11-20")
    _version(manager_role_client, "2036-11-15", ("PUT", "flags", {"flag_id": sea, "unit_ids": [uid], "value": True}))
    body = _board(manager_client, category_ids=[cat["id"]], flag_ids=[sea])
    row = next(u for u in body["units"] if u["unit_id"] == uid)
    assert row["off"] == [["2036-11-01", "2036-11-14", "filtered"]]
    assert row["flags"] == []                       # свойства строки — на первый день периода
    bars = [b for b in body["bars"] if b["reservation_id"] == r["id"]]
    assert [(b["unit_id"], b["start"], b["end"]) for b in bars] == [(uid, "2036-11-05", "2036-11-20")]
    occ = manager_client.get(f"{API}/occupancy", params={**MONTH, "category_ids": cat["id"],
                                                         "flag_ids": sea}).json()
    days = dict(zip(occ["days"], occ["total"]["days"], strict=True))
    assert (days["2036-11-10"]["total"], days["2036-11-10"]["living"]) == (0, 0)
    assert (days["2036-11-16"]["total"], days["2036-11-16"]["living"]) == (1, 1)


def test_absent_days_marked(manager_role_client, manager_client, today):
    today("2036-11-01")
    cat = make_category(manager_role_client, n_units=2)
    gone = cat["units"][1]["id"]
    _version(manager_role_client, "2036-11-15", ("DELETE", f"units/{gone}", {}),
             ("POST", "units", {"label": cat["code"] + "-new", "category_id": cat["id"]}))
    rows = _rows(manager_client, category_ids=[cat["id"]])
    assert rows[gone]["off"] == [["2036-11-15", "2036-11-30", "absent"]]
    assert rows[cat["units"][0]["id"]]["off"] == []
    new = next(u for u in rows.values() if u["label"] == cat["code"] + "-new")
    assert new["off"] == [["2036-11-01", "2036-11-14", "absent"]]
    assert new["labels"] == [{"from": "2036-11-15", "label": cat["code"] + "-new"}]
    # в фонде, но вне фильтра — «filtered», дальше — «absent»
    sea = _flag(manager_role_client)
    _version(manager_role_client, "2036-11-20",
             ("PUT", "flags", {"flag_id": sea, "unit_ids": [new["unit_id"]], "value": True}))
    row = _rows(manager_client, category_ids=[cat["id"]], flag_ids=[sea])[new["unit_id"]]
    assert row["off"] == [["2036-11-01", "2036-11-14", "absent"], ["2036-11-15", "2036-11-19", "filtered"]]


def test_label_change_listed(manager_role_client, manager_client, today):
    today("2036-11-01")
    cat = make_category(manager_role_client, n_units=1)
    second = make_category(manager_role_client, n_units=1)
    u = cat["units"][0]
    _version(manager_role_client, "2036-11-15",
             ("PUT", f"units/{u['id']}", {"label": u["label"] + "-н", "category_id": second["id"]}))
    row = _rows(manager_client, category_ids=[cat["id"], second["id"]])[u["id"]]
    assert row["label"] == u["label"] and row["category_id"] == cat["id"]
    assert row["labels"] == [{"from": "2036-11-01", "label": u["label"]},
                             {"from": "2036-11-15", "label": u["label"] + "-н"}]
    assert row["categories"] == [{"from": "2036-11-01", "category_id": cat["id"]},
                                 {"from": "2036-11-15", "category_id": second["id"]}]
    # фильтр по второй категории: строка есть, дни до 15.11 — вне фильтра
    only = _rows(manager_client, category_ids=[second["id"]])[u["id"]]
    assert only["off"] == [["2036-11-01", "2036-11-14", "filtered"]]


def test_load_metric(manager_role_client, manager_client, today):
    """Загрузка строки = занятые ночи / ночи в фонде за период: объект в фонде 20 ночей
    (выведен с 21.11), занят 5 → 0.25; пустой объект — 0."""
    today("2036-11-01")
    cat = make_category(manager_role_client, n_units=2)
    a, b = (u["id"] for u in cat["units"])
    create_res(manager_client, cat, "2036-11-03", "2036-11-08", pins={0: a})
    _version(manager_role_client, "2036-11-21", ("DELETE", f"units/{a}", {}))
    rows = _rows(manager_client, category_ids=[cat["id"]])
    assert rows[a]["load"] == 0.25
    assert rows[b]["load"] == 0.0


def test_day_board_filters_by_group_and_flags(manager_role_client, manager_client):
    corp, villas = _groups(manager_role_client, "Корпус", "Виллы")
    rooms = make_category(manager_role_client, n_units=1, kind="room", group_id=corp)
    vil = make_category(manager_role_client, n_units=2, kind="villa", group_id=villas)
    sea = _flag(manager_role_client)
    _set_flag(manager_role_client, sea, [vil["units"][0]["id"]])
    day = "2036-12-05"
    rr = create_res(manager_client, rooms, day, "2036-12-08")
    v1 = create_res(manager_client, vil, day, "2036-12-08", pins={0: vil["units"][0]["id"]})
    v2 = create_res(manager_client, vil, day, "2036-12-08", pins={0: vil["units"][1]["id"]})

    def arrivals(**params) -> set[int]:
        r = manager_client.get(f"{API}/day", params={"date": day, **params})
        assert r.status_code == 200, r.text
        return {x["reservation_id"] for x in r.json()["arrivals"]}
    assert arrivals(group_ids=[corp, villas]) == {rr["id"], v1["id"], v2["id"]}
    assert arrivals(group_ids=[villas]) == {v1["id"], v2["id"]}
    assert arrivals(group_ids=[villas], flag_ids=[sea]) == {v1["id"]}
    assert arrivals(category_ids=[rooms["id"]]) == {rr["id"]}
    assert arrivals(group_ids=[corp, villas], kinds=["room"]) == {rr["id"]}


def test_month_query_budget_440_units(manager_client, big_fund, sql_counter):
    """31 день × 440 объектов с фильтрами по дням — бюджет ≤ 30 запросов (§6)."""
    params = {"first": "2029-06-01", "last": "2029-07-01", "kinds": ["room"], "flag_ids": []}
    with sql_counter() as c:
        r = manager_client.get(f"{API}/board/units", params=params)
    assert r.status_code == 200
    body = r.json()
    assert len(body["days"]) == 31 and len(body["units"]) >= 440 and len(body["bars"]) >= 300
    assert any(u["load"] > 0 for u in body["units"])
    assert c["total"] <= 30, sorted(c["by_statement"].items(), key=lambda x: -x[1])[:3]
    with sql_counter() as c:
        r = manager_client.get(f"{API}/occupancy", params=params)
    assert r.status_code == 200
    assert c["total"] <= 30, sorted(c["by_statement"].items(), key=lambda x: -x[1])[:3]


def test_removed_params_422(manager_client):
    base = {"first": "2036-11-01", "last": "2036-11-02"}
    for path, extra in (("/board/units", base), ("/occupancy", base), ("/day", {"date": "2036-11-01"})):
        for old in ("building", "category_id", "kind"):
            r = manager_client.get(f"{API}{path}", params={**extra, old: "1"})
            assert r.status_code == 422, (path, old, r.text)


def test_occupancy_level_ignores_vip_and_search(manager_role_client, manager_client, occupancy_client):
    """C1: поиск и VIP опираются на данные гостей — уровню occupancy они не применяются ни на
    шахматке, ни на табло дня (иначе по числу полос подбиралась бы фамилия или VIP)."""
    cat = make_category(manager_role_client, n_units=2)
    g = make_guest(manager_client, "Скрытный" + uniq(), level="vip")
    day = "2036-12-10"
    create_res(manager_client, cat, day, "2036-12-12", [(g["id"], "main", None, None)])
    create_res(manager_client, cat, day, "2036-12-12")
    win = {"first": day, "last": "2036-12-12", "category_ids": cat["id"]}
    for params in ({"vip": 1}, {"q": g["last_name"]}, {"q": "нет-такого"}):
        assert len(occupancy_client.get(f"{API}/board/units", params={**win, **params}).json()["bars"]) == 2
        arr = occupancy_client.get(f"{API}/day", params={"date": day, "category_ids": cat["id"], **params}).json()
        assert len(arr["arrivals"]) == 2, params
    assert len(manager_client.get(f"{API}/board/units", params={**win, "vip": 1}).json()["bars"]) == 1
