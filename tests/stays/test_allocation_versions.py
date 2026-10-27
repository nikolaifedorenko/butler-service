"""Распределение на границах версий фонда (спецификация stays-fund-versions §5, §14): сегменты
режутся на части в границах, прошлое заморожено и без объекта (находка L1 аудита), доска склеивает
соседние части с одним объектом, закрепление сегмента — на всех частях, OOO там, где объекта нет
в фонде, — предупреждение hold_absent."""
from __future__ import annotations

from sqlalchemy import select

from .helpers import API, create_res, make_category, units_of


def _version(setup_client, valid_from: str, *edits) -> None:
    """Опубликовать версию фонда с даты: edits — (метод, путь, тело) правок черновика."""
    r = setup_client.post(f"{API}/fund/draft", json={"valid_from": valid_from})
    assert r.status_code == 200, r.text
    rev = r.json()["rev"]
    for method, path, body in edits:
        if method == "DELETE":
            resp = setup_client.delete(f"{API}/fund/draft/{path}", params={"rev": rev})
        else:
            resp = setup_client.request(method, f"{API}/fund/draft/{path}", json={"rev": rev, **body})
        assert resp.status_code == 200, resp.text
        rev = resp.json()["rev"]
    resp = setup_client.post(f"{API}/fund/draft/publish", json={"rev": rev})
    assert resp.status_code == 200, resp.text


def _rename(cat: dict, i: int) -> tuple:
    u = cat["units"][i]
    return "PUT", f"units/{u['id']}", {"label": u["label"] + "-н", "category_id": cat["id"]}


def _rows(db, rid: int) -> dict[int, tuple]:
    from app.modules.stays.adapters.orm import Assignment

    db.expire_all()
    return {a.seg_index: (a.unit_id, bool(a.pinned))
            for a in db.scalars(select(Assignment).where(Assignment.reservation_id == rid))}


def _put(c, res, **changes):
    body = {**{k: res[k] for k in ("number", "check_in", "check_out", "category_id", "early", "late",
                                   "group_id", "note", "declined_butler")},
            "moves": res["moves"], "occupants": res["occupants"], "companions": res["companions"],
            "logistics": res["logistics"], "version": res["version"], **changes}
    return c.put(f"{API}/reservations/{res['id']}", json=body)


def test_past_piece_without_unit_not_placed(manager_role_client, manager_client, today):
    """L1: сегмент 0 не получил объект (единственная вилла занята), позже виллу освободили —
    закончившийся до сегодня сегмент остаётся «без объекта», задним числом не размещается."""
    today("2035-03-01")
    villa = make_category(manager_role_client, n_units=1)
    other = make_category(manager_role_client, n_units=1)
    a = create_res(manager_client, villa, "2035-03-02", "2035-03-25")
    b = create_res(manager_client, villa, "2035-03-02", "2035-03-12",
                   moves=[{"move_date": "2035-03-08", "category_id": other["id"]}])
    assert units_of(b) == [None, other["units"][0]["id"]]
    today("2035-03-10")
    st = manager_client.post(f"{API}/reservations/{a['id']}/status",
                             json={"status": "cancelled", "version": a["version"]})
    assert st.status_code == 200, st.text
    got = manager_client.get(f"{API}/reservations/{b['id']}").json()
    assert units_of(got) == [None, other["units"][0]["id"]]


def test_board_merges_pieces_same_unit(manager_role_client, manager_client, today, db):
    """Граница версии внутри сегмента режет его на две части; объект тот же — одна полоса."""
    today("2035-04-01")
    cat = make_category(manager_role_client, n_units=1)
    uid = cat["units"][0]["id"]
    r = create_res(manager_client, cat, "2035-04-05", "2035-04-15")
    _version(manager_role_client, "2035-04-10", _rename(cat, 0))
    assert _rows(db, r["id"]) == {0: (uid, False), 1: (uid, False)}
    board = manager_client.get(f"{API}/board/units", params={"first": "2035-04-01", "last": "2035-04-20",
                                                             "category_id": cat["id"]}).json()
    bars = [b for b in board["bars"] if b["reservation_id"] == r["id"]]
    assert [(b["seg_index"], b["unit_id"], b["start"], b["end"]) for b in bars] == [
        (0, uid, "2035-04-05", "2035-04-15")]


def test_pin_segment_pins_all_pieces(manager_role_client, manager_client, today, db):
    today("2035-05-01")
    cat = make_category(manager_role_client, n_units=2)
    first, second = (u["id"] for u in cat["units"])
    r = create_res(manager_client, cat, "2035-05-05", "2035-05-15")
    _version(manager_role_client, "2035-05-10", _rename(cat, 0))
    assert _rows(db, r["id"]) == {0: (first, False), 1: (first, False)}
    doc = manager_client.get(f"{API}/reservations/{r['id']}").json()
    put = _put(manager_client, doc, pins={"0": second})
    assert put.status_code == 200, put.text
    assert _rows(db, r["id"]) == {0: (second, True), 1: (second, True)}
    seg = put.json()["result"]["segments"][0]
    assert (seg["unit_id"], seg["pinned"]) == (second, True)
    doc = manager_client.get(f"{API}/reservations/{r['id']}").json()
    assert _put(manager_client, doc, pins={"0": None}).status_code == 200      # «авто» — со всех частей
    assert {k: p for k, (_u, p) in _rows(db, r["id"]).items()} == {0: False, 1: False}


def test_publish_version_reallocates_future_only(manager_role_client, manager_client, today, db):
    """Версия с D выводит объект второго сегмента: до D он остаётся в нём, с D — переезжает;
    первый сегмент, закончившийся до D, не трогается."""
    today("2035-06-01")
    cat = make_category(manager_role_client, n_units=2)
    first, second = (u["id"] for u in cat["units"])
    r = create_res(manager_client, cat, "2035-06-02", "2035-06-12",
                   moves=[{"move_date": "2035-06-05", "category_id": cat["id"]}])
    assert units_of(r) == [first, second]                    # переезд — в другой объект
    _version(manager_role_client, "2035-06-08", ("DELETE", f"units/{second}", {}))
    assert _rows(db, r["id"]) == {0: (first, False), 1000: (second, False), 1001: (first, False)}
    board = manager_client.get(f"{API}/board/units", params={"first": "2035-06-01", "last": "2035-06-15",
                                                             "category_id": cat["id"]}).json()
    bars = [b for b in board["bars"] if b["reservation_id"] == r["id"]]
    assert [(b["seg_index"], b["unit_id"], b["start"], b["end"]) for b in bars] == [
        (0, first, "2035-06-02", "2035-06-05"), (1000, second, "2035-06-05", "2035-06-08"),
        (1001, first, "2035-06-08", "2035-06-12")]


def test_later_version_keeps_earlier_pieces(manager_role_client, manager_client, today, db):
    """Новая граница добавляет часть справа: индексы и объекты прежних частей не меняются,
    закончившаяся до сегодня часть заморожена, с границы — другой объект."""
    today("2035-07-01")
    cat = make_category(manager_role_client, n_units=2)
    first, second = (u["id"] for u in cat["units"])
    r = create_res(manager_client, cat, "2035-07-02", "2035-07-20")
    _version(manager_role_client, "2035-07-05", _rename(cat, 1))
    assert _rows(db, r["id"]) == {0: (first, False), 1: (first, False)}
    today("2035-07-10")
    _version(manager_role_client, "2035-07-12", ("DELETE", f"units/{first}", {}))
    assert _rows(db, r["id"]) == {0: (first, False), 1: (first, False), 2: (second, False)}


def test_hold_on_absent_unit_warns(manager_role_client, manager_client, today):
    """OOO на дни, когда объекта нет в фонде (выведен версией с вечера D), — предупреждение
    hold_absent с дня D."""
    today("2035-08-01")
    cat = make_category(manager_role_client, n_units=2)
    gone = cat["units"][1]
    _version(manager_role_client, "2035-08-10", ("DELETE", f"units/{gone['id']}", {}))
    h = manager_client.post(f"{API}/holds", json={"unit_id": gone["id"], "start": "2035-08-08",
                                                  "end": "2035-08-14", "kind": "ooo", "title": "Ремонт"})
    assert h.status_code == 200, h.text
    text = f"объекта {gone['label']} нет в фонде 10.08–14.08"
    assert any(w["kind"] == "hold_absent" and text in w["text"] for w in h.json()["diff"]["warnings_added"])
    board = manager_client.get(f"{API}/board/units", params={"first": "2035-08-01", "last": "2035-08-20",
                                                             "category_id": cat["id"]}).json()
    assert [w["kind"] for w in board["warnings"] if text in w["text"]] == ["hold_absent"]
