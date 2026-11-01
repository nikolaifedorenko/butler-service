"""Шахматка, часть 2, задача 4: API блоков — сетка «категория × ночь», помощник «заполнить» и
быстрая правка, сужение дат, проверки (422/409), версия, журнал, список с нехваткой, окно
предпросмотра ±62 дня для длинного блока (Review Focus 5)."""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import select

from app.core.audit import AuditLog
from app.modules.stays.application import preview

from .helpers import API, create_res, make_category
from .test_allocation_versions import _version
from .test_overbooking import no_overbook_client  # noqa: F401  (фикстура)
from .test_preview import dump


def _nights(first: str, n: int) -> list[str]:
    d = dt.date.fromisoformat(first)
    return [(d + dt.timedelta(days=i)).isoformat() for i in range(n)]


def _block(c, title, start, end, grid=None, **params):
    return c.post(f"{API}/blocks", params=params, json={"title": title, "start": start, "end": end,
                                                        "grid": grid if grid is not None else {}})


def _grid(cat, first, n, qty):
    return {cat["id"]: {d: qty for d in _nights(first, n)}}


def test_block_grid_crud(manager_role_client, manager_client, db):
    a = make_category(manager_role_client, n_units=3)
    b = make_category(manager_role_client, n_units=2)
    grid = {a["id"]: {"2045-03-10": 2, "2045-03-11": 3}, b["id"]: {"2045-03-11": 1}}
    r = _block(manager_client, "Свадьба", "2045-03-10", "2045-03-13", grid)
    assert r.status_code == 200, r.text
    blk = r.json()["result"]
    assert blk["version"] == 1 and blk["dropped"] == []
    assert blk["grid"] == {str(a["id"]): {"2045-03-10": 2, "2045-03-11": 3}, str(b["id"]): {"2045-03-11": 1}}
    card = manager_client.get(f"{API}/blocks/{blk['id']}").json()
    assert card["grid"] == blk["grid"] and card["short"] == [] and card["nights"] == 3 and card["placed"] == 6
    assert card["top"] == [{"category_id": a["id"], "code": a["code"], "max": 3},
                           {"category_id": b["id"], "code": b["code"], "max": 1}]
    # сетка целиком: категория b уходит, у a меняются остатки
    new = {a["id"]: {"2045-03-10": 1, "2045-03-12": 2}}
    put = manager_client.put(f"{API}/blocks/{blk['id']}", json={"title": "Свадьба-2", "start": "2045-03-10",
                                                                "end": "2045-03-13", "grid": new, "version": 1})
    assert put.status_code == 200, put.text
    assert put.json()["result"]["grid"] == {str(a["id"]): {"2045-03-10": 1, "2045-03-12": 2}}
    assert put.json()["result"]["version"] == 2
    gone = manager_client.delete(f"{API}/blocks/{blk['id']}", params={"version": 2})
    assert gone.status_code == 200 and gone.json()["result"] == {"id": blk["id"], "deleted": True}
    assert manager_client.get(f"{API}/blocks/{blk['id']}").status_code == 404
    rows = db.scalars(select(AuditLog).where(AuditLog.action == "stays_block", AuditLog.target == f"block:{blk['id']}")
                      .order_by(AuditLog.id)).all()
    diffs = [json.loads(x.payload_json)["diff"] for x in rows]
    assert len(diffs) == 3 and diffs[0]["title"] == [None, "Свадьба"]
    assert diffs[1]["title"] == ["Свадьба", "Свадьба-2"] and diffs[1]["version"] == [1, 2]
    assert diffs[1]["grid"][0][str(b["id"])] == {"2045-03-11": 1}                  # было → стало
    assert diffs[2]["title"] == ["Свадьба-2", None]


def test_block_fill_helper_and_quick_edit(manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=5)
    blk = _block(manager_client, "Форум", "2045-04-10", "2045-04-20").json()["result"]
    url = f"{API}/blocks/{blk['id']}/nights"
    # «заполнить»: категория, с–по (ночи включительно), количество
    fill = manager_client.patch(url, json={"version": 1, "category_id": cat["id"], "first": "2045-04-10",
                                           "last": "2045-04-19", "quantity": 3})
    assert fill.status_code == 200, fill.text
    assert fill.json()["result"]["version"] == 2
    assert fill.json()["result"]["grid"][str(cat["id"])] == {d: 3 for d in _nights("2045-04-10", 10)}
    # быстрая правка выделенных ночей и «убрать ночи»
    edit = manager_client.patch(url, json={"version": 2, "category_id": cat["id"], "first": "2045-04-12",
                                           "last": "2045-04-13", "quantity": 5})
    assert edit.status_code == 200
    off = manager_client.patch(url, json={"version": 3, "category_id": cat["id"], "first": "2045-04-10",
                                          "last": "2045-04-11", "quantity": 0})
    assert off.status_code == 200, off.text
    got = manager_client.get(f"{API}/blocks/{blk['id']}").json()
    assert got["grid"][str(cat["id"])] == {**{d: 3 for d in _nights("2045-04-14", 6)}, "2045-04-12": 5,
                                           "2045-04-13": 5}
    assert "2045-04-10" not in got["grid"][str(cat["id"])] and got["version"] == 4
    # ночь вне блока — 422, устаревшая версия — 409
    out = manager_client.patch(url, json={"version": 4, "category_id": cat["id"], "first": "2045-04-19",
                                          "last": "2045-04-20", "quantity": 1})
    assert out.status_code == 422, out.text
    assert manager_client.patch(url, json={"version": 1, "category_id": cat["id"], "first": "2045-04-15",
                                           "last": "2045-04-15", "quantity": 1}).status_code == 409
    # убрать все ночи категории — строка категории исчезает
    allgone = manager_client.patch(url, json={"version": 4, "category_id": cat["id"], "first": "2045-04-10",
                                              "last": "2045-04-19", "quantity": 0})
    assert allgone.status_code == 200 and allgone.json()["result"]["grid"] == {}


def test_block_narrow_dates_drops_nights(manager_role_client, manager_client, db):
    cat = make_category(manager_role_client, n_units=3)
    blk = _block(manager_client, "Конгресс", "2045-05-10", "2045-05-16", _grid(cat, "2045-05-10", 6, 2)) \
        .json()["result"]
    body = {"title": "Конгресс", "start": "2045-05-12", "end": "2045-05-14", "version": 1}
    before = dump(db)
    pv = manager_client.put(f"{API}/blocks/{blk['id']}", params={"preview": 1}, json=body)
    assert pv.status_code == 200, pv.text
    assert dump(db) == before
    assert [(x["night"], x["quantity"]) for x in pv.json()["result"]["dropped"]] == [
        ("2045-05-10", 2), ("2045-05-11", 2), ("2045-05-14", 2), ("2045-05-15", 2)]      # видно в предпросмотре
    assert pv.json()["result"]["grid"][str(cat["id"])] == {"2045-05-12": 2, "2045-05-13": 2}
    sv = manager_client.put(f"{API}/blocks/{blk['id']}", json=body)
    assert sv.status_code == 200 and sv.json()["diff"] == pv.json()["diff"]
    assert manager_client.get(f"{API}/blocks/{blk['id']}").json()["grid"] == {
        str(cat["id"]): {"2045-05-12": 2, "2045-05-13": 2}}
    # сетка целиком с ночью вне новых дат — 422, а не молчаливое обрезание
    bad = manager_client.put(f"{API}/blocks/{blk['id']}", json={
        **body, "version": 2, "grid": _grid(cat, "2045-05-10", 6, 1)})
    assert bad.status_code == 422, bad.text
    # даты: не короче одной ночи
    assert manager_client.put(f"{API}/blocks/{blk['id']}", json={**body, "version": 2, "end": "2045-05-12"}) \
        .status_code == 422


def test_block_category_absent_422(manager_role_client, manager_client, today):
    today("2045-06-01")
    cat = make_category(manager_role_client, n_units=2)            # в фонде с 01.06
    r = _block(manager_client, "Ранний", "2045-05-20", "2045-05-23", _grid(cat, "2045-05-20", 3, 1))
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == f"Категории №{cat['id']} нет в фонде на ночь 20.05.2045"
    assert _block(manager_client, "Мимо", "2045-06-10", "2045-06-12", {10 ** 9: {"2045-06-10": 1}}).status_code == 422
    # ночь вне [start, end) — 422
    assert _block(manager_client, "Вне", "2045-06-10", "2045-06-12", _grid(cat, "2045-06-12", 1, 1)).status_code == 422
    assert _block(manager_client, "Вне", "2045-06-10", "2045-06-12", _grid(cat, "2045-06-09", 1, 1)).status_code == 422
    assert _block(manager_client, "Ок", "2045-06-10", "2045-06-12", _grid(cat, "2045-06-10", 2, 1)).status_code == 200
    # категория, выведенная из фонда версией, на последующие ночи не подходит
    _version(manager_role_client, "2045-06-20", *[("DELETE", f"units/{u['id']}", {}) for u in cat["units"]],
             ("DELETE", f"categories/{cat['id']}", {}))
    gone = _block(manager_client, "Поздний", "2045-06-19", "2045-06-22", _grid(cat, "2045-06-19", 3, 1))
    assert gone.status_code == 422 and "21.06.2045" not in gone.json()["detail"]


def test_version_conflict_409(manager_role_client, manager_client, db):
    cat = make_category(manager_role_client, n_units=2)
    blk = _block(manager_client, "Версия", "2045-07-10", "2045-07-12", _grid(cat, "2045-07-10", 2, 1)).json()["result"]
    body = {"title": "Версия-2", "start": "2045-07-10", "end": "2045-07-12", "version": 1}
    assert manager_client.put(f"{API}/blocks/{blk['id']}", json=body).status_code == 200
    before = dump(db)
    assert manager_client.put(f"{API}/blocks/{blk['id']}", json=body).status_code == 409
    assert manager_client.put(f"{API}/blocks/{blk['id']}", params={"preview": 1}, json=body).status_code == 409
    assert manager_client.delete(f"{API}/blocks/{blk['id']}", params={"version": 1}).status_code == 409
    assert dump(db) == before
    assert manager_client.get(f"{API}/blocks/{blk['id']}").json()["title"] == "Версия-2"


def test_past_edits_allowed_and_audited(manager_role_client, manager_client, db, today):
    today("2045-08-01")
    cat = make_category(manager_role_client, n_units=2)
    today("2045-08-20")
    blk = _block(manager_client, "Прошлый", "2045-08-05", "2045-08-08", _grid(cat, "2045-08-05", 3, 1)).json()["result"]
    r = manager_client.patch(f"{API}/blocks/{blk['id']}/nights", json={
        "version": 1, "category_id": cat["id"], "first": "2045-08-06", "last": "2045-08-07", "quantity": 2})
    assert r.status_code == 200, r.text
    assert manager_client.delete(f"{API}/blocks/{blk['id']}", params={"version": 2}).status_code == 200
    assert len(db.scalars(select(AuditLog).where(AuditLog.action == "stays_block",
                                                 AuditLog.target == f"block:{blk['id']}")).all()) == 3


def test_block_short_in_card_and_list(manager_role_client, manager_client, today):
    today("2045-09-01")
    cat = make_category(manager_role_client, n_units=2)
    grid = {cat["id"]: {"2045-09-10": 3, "2045-09-11": 3, "2045-09-12": 1}}
    blk = _block(manager_client, "Много", "2045-09-10", "2045-09-13", grid).json()["result"]
    ok = _block(manager_client, "Хватает", "2045-09-20", "2045-09-23", _grid(cat, "2045-09-20", 3, 1)).json()["result"]
    card = manager_client.get(f"{API}/blocks/{blk['id']}").json()
    assert card["short"] == [{"category_id": cat["id"], "first": "2045-09-10", "last": "2045-09-11", "missing": 1}]
    assert (card["placed"], card["missing"], card["short"] != []) == (7 - 2, 2, True)
    rows = manager_client.get(f"{API}/blocks", params={"category_ids": cat["id"], "short_only": "true"}).json()
    assert [x["id"] for x in rows["rows"]] == [blk["id"]] and rows["rows"][0]["short"] is True
    allrows = manager_client.get(f"{API}/blocks", params={"category_ids": cat["id"]}).json()["rows"]
    assert {x["id"]: x["short"] for x in allrows} == {blk["id"]: True, ok["id"]: False}
    # нехватка видна и шахматке, блок не уменьшился
    assert manager_client.get(f"{API}/blocks/{blk['id']}").json()["grid"][str(cat["id"])]["2045-09-10"] == 3


def test_lists_filters_sort(manager_role_client, manager_client):
    a = make_category(manager_role_client, n_units=4)
    b = make_category(manager_role_client, n_units=4)
    ids = {}
    for key, title, s, e, grid in (
            ("x", "Форум", "2046-01-10", "2046-01-14", {a["id"]: {"2046-01-10": 4, "2046-01-11": 1}}),
            ("y", "Свадьба", "2046-01-20", "2046-01-22", {a["id"]: {"2046-01-20": 2}, b["id"]: {"2046-01-21": 3}}),
            ("z", "Конгресс", "2046-03-01", "2046-03-05", {b["id"]: {"2046-03-01": 1}})):
        ids[key] = _block(manager_client, title, s, e, grid).json()["result"]["id"]

    def rows(**p):
        r = manager_client.get(f"{API}/blocks", params={"category_ids": [a["id"], b["id"]], **p})
        assert r.status_code == 200, r.text
        return [x["id"] for x in r.json()["rows"]]
    assert rows() == [ids["x"], ids["y"], ids["z"]]
    assert rows(sort="title") == [ids["z"], ids["y"], ids["x"]]
    assert rows(sort="nights", dir="desc") == [ids["x"], ids["z"], ids["y"]]
    assert rows(q="свад") == [ids["y"]]
    assert rows(first="2046-01-15", last="2046-02-28") == [ids["y"]]            # пересечение периода
    only_b = manager_client.get(f"{API}/blocks", params={"category_ids": b["id"]}).json()
    assert [x["id"] for x in only_b["rows"]] == [ids["y"], ids["z"]] and only_b["total"] == 2
    page = manager_client.get(f"{API}/blocks", params={"category_ids": [a["id"], b["id"]], "limit": 1, "offset": 2}).json()
    assert page["total"] == 3 and [x["id"] for x in page["rows"]] == [ids["z"]]
    top = next(x for x in manager_client.get(f"{API}/blocks", params={"category_ids": a["id"]}).json()["rows"]
               if x["id"] == ids["x"])
    assert (top["title"], top["start"], top["end"], top["nights"], top["top"], top["placed"], top["short"]) == (
        "Форум", "2046-01-10", "2046-01-14", 4, [{"category_id": a["id"], "code": a["code"], "max": 4}], 5, False)
    assert manager_client.get(f"{API}/blocks", params={"sort": "nope"}).status_code == 422
    assert manager_client.get(f"{API}/blocks", params={"last": "2046-01-01"}).status_code == 422


def test_visible_to_all_levels_with_titles(manager_role_client, manager_client, mgmt_client, occupancy_client,
                                           employee_client):
    cat = make_category(manager_role_client, n_units=2)
    blk = _block(manager_client, "Делегация", "2047-01-10", "2047-01-12", _grid(cat, "2047-01-10", 2, 1)).json()["result"]
    for c in (manager_client, mgmt_client, occupancy_client):
        r = c.get(f"{API}/blocks", params={"category_ids": cat["id"]})
        assert r.status_code == 200, r.text
        assert [(x["id"], x["title"]) for x in r.json()["rows"]] == [(blk["id"], "Делегация")]
        assert c.get(f"{API}/blocks/{blk['id']}").json()["title"] == "Делегация"
    assert employee_client.get(f"{API}/blocks").status_code == 403
    for c in (mgmt_client, occupancy_client):
        assert _block(c, "Чужой", "2047-02-10", "2047-02-12").status_code == 403


def test_block_preview_equals_save_and_overbook(manager_role_client, manager_client, db):
    cat = make_category(manager_role_client, n_units=1)
    create_res(manager_client, cat, "2048-01-10", "2048-01-14")
    body = {"title": "Гендир", "start": "2048-01-11", "end": "2048-01-13", "grid": _grid(cat, "2048-01-11", 2, 1)}
    before = dump(db)
    pv = manager_client.post(f"{API}/blocks", params={"preview": 1}, json=body)
    assert pv.status_code == 200 and dump(db) == before
    sv = manager_client.post(f"{API}/blocks", json=body)
    assert sv.status_code == 200 and pv.json()["diff"] == sv.json()["diff"]
    # блок главнее подтверждённой брони — без объекта остаётся бронь
    assert "overbooked" in {w["kind"] for w in sv.json()["diff"]["warnings_added"]}


def test_long_block_preview_window(manager_role_client, manager_client, big_fund, sql_counter, monkeypatch):
    """Review Focus 5: блок на 90 ночей × 6 категорий — предпросмотр и сохранение в окне ±62 дня,
    шахматка 440 × 31 с таким блоком — не больше 30 запросов."""
    from sqlalchemy import select as sel

    from app.core.db import SessionLocal
    from app.modules.stays.adapters.orm import CategoryState

    with SessionLocal() as s:
        big = list(s.scalars(sel(CategoryState.category_id).where(CategoryState.code.in_(("BIGDLX", "BIGSTE", "BIGVIL")))
                             .distinct()))
    extra = [make_category(manager_role_client, n_units=1)["id"] for _ in range(3)]
    first = "2029-06-01"
    nights = _nights(first, 90)
    grid = {cid: {d: 1 for d in nights} for cid in [*big, *extra]}
    assert len(grid) == 6 and sum(len(v) for v in grid.values()) == 540
    windows = []
    real = preview.take_snapshot
    monkeypatch.setattr(preview, "take_snapshot", lambda db, window=None, duty=None: (
        windows.append(window), real(db, window, duty))[1])
    body = {"title": "Длинный", "start": first, "end": "2029-08-30", "grid": grid}
    pv = manager_client.post(f"{API}/blocks", params={"preview": 1}, json=body)
    assert pv.status_code == 200, pv.text
    lo, hi = dt.date(2029, 6, 1) - dt.timedelta(days=62), dt.date(2029, 8, 29) + dt.timedelta(days=62)
    assert windows == [(lo, hi), (lo, hi)]                         # окно ограничено ±62 днями вокруг блока
    assert (hi - lo).days + 1 == 62 + 90 + 62
    sv = manager_client.post(f"{API}/blocks", json=body)
    assert sv.status_code == 200, sv.text
    bid = sv.json()["result"]["id"]
    try:
        with sql_counter() as c:
            r = manager_client.get(f"{API}/board/units", params=big_fund)
        assert r.status_code == 200
        assert c["total"] <= 30, sorted(c["by_statement"].items(), key=lambda x: -x[1])[:3]
        card = manager_client.get(f"{API}/blocks/{bid}")
        assert card.status_code == 200 and len(card.json()["grid"]) == 6
    finally:
        manager_client.delete(f"{API}/blocks/{bid}", params={"version": 1})


def test_nights_range_checked_before_building(manager_role_client, manager_client):
    """PATCH с огромным диапазоном — 422 сразу, без построения миллионов ночей под замком."""
    cat = make_category(manager_role_client, n_units=1)
    blk = _block(manager_client, "Узкий", "2049-01-10", "2049-01-12", _grid(cat, "2049-01-10", 2, 1)).json()["result"]
    url = f"{API}/blocks/{blk['id']}/nights"
    for first, last in (("2000-01-01", "2200-12-31"), ("2049-01-09", "2049-01-10"), ("0001-01-01", "9999-12-31")):
        r = manager_client.patch(url, json={"version": 1, "category_id": cat["id"], "first": first, "last": last,
                                            "quantity": 1})
        assert r.status_code == 422, (first, r.text)
    assert manager_client.patch(url, json={"version": 1, "category_id": cat["id"], "first": "2049-01-10",
                                           "last": "2049-01-10", "quantity": 501}).status_code == 422
    assert _block(manager_client, "  ", "2049-02-10", "2049-02-12").status_code == 422
    assert _block(manager_client, "", "2049-02-10", "2049-02-12").status_code == 422
    assert _block(manager_client, "Огромный", "2049-02-10", "2049-02-12", _grid(cat, "2049-02-10", 1, 501)) \
        .status_code == 422
    assert _block(manager_client, "Рано", "0001-01-01", "0001-02-01").status_code == 422


def test_long_block_overbook_beyond_window_needs_perm(manager_role_client, manager_client, no_overbook_client):
    """Овербукинг, появляющийся только после 124-го дня блока (за окном предпросмотра), всё равно
    проверяется по полному состоянию: без stays.overbook — 409; предпросмотр — 200 с отказом."""
    cat = make_category(manager_role_client, n_units=1)
    create_res(manager_client, cat, "2050-06-01", "2050-06-04")                    # день ~151 от начала блока
    body = {"title": "Длинный", "start": "2050-01-01", "end": "2050-07-20", "grid": _grid(cat, "2050-01-01", 200, 1)}
    pv = no_overbook_client.post(f"{API}/blocks", params={"preview": 1}, json=body)
    assert pv.status_code == 200 and pv.json()["overbook_refused"], pv.text
    r = no_overbook_client.post(f"{API}/blocks", json=body)
    assert r.status_code == 409 and r.json()["detail"]["overbook"] is True
    assert manager_client.get(f"{API}/blocks", params={"q": "Длинный"}).json()["total"] == 0
    assert manager_client.post(f"{API}/blocks", json=body).status_code == 200      # с правом — сохраняется


def test_adjacent_blocks_no_false_overbook(manager_role_client, manager_client, no_overbook_client):
    """Финальное ревью, Important 1: 2 объекта, блок P на ночь 10, подтверждённая бронь на ночи
    10–11; блок Q на ночь 11 становится в объект блока P, бронь — во второй объект, овербукинга
    нет, поэтому сохранение без stays.overbook проходит."""
    cat = make_category(manager_role_client, n_units=2)
    create_res(manager_client, cat, "2051-03-10", "2051-03-12")
    assert _block(manager_client, "P", "2051-03-10", "2051-03-11", _grid(cat, "2051-03-10", 1, 1)).status_code == 200
    pv = _block(no_overbook_client, "Q", "2051-03-11", "2051-03-12", _grid(cat, "2051-03-11", 1, 1), preview=1)
    assert pv.status_code == 200 and "overbook_refused" not in pv.json(), pv.text
    r = _block(no_overbook_client, "Q", "2051-03-11", "2051-03-12", _grid(cat, "2051-03-11", 1, 1))
    assert r.status_code == 200, r.text
    assert "overbooked" not in {w["kind"] for w in r.json()["diff"]["warnings_added"]}
