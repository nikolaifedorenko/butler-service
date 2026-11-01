"""Шахматка, часть 2, задача 4: API OOO — половинки суток, проверки (422/409), версия, предпросмотр ≡
сохранение, журнал «было → стало», список с фильтрами и сортировкой, видимость всем уровням."""
from __future__ import annotations

import json

from sqlalchemy import select

from app.core.audit import AuditLog

from .helpers import API, create_res, make_category, units_of
from .test_allocation_versions import _version
from .test_preview import dump


def _ooo(c, unit_id, start, end, reason="Ремонт", **kw):
    return c.post(f"{API}/ooo", json={"unit_id": unit_id, "start": start, "end": end, "reason": reason, **kw})


def test_ooo_crud_halves_and_flags(manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=2)
    u1, u2 = (u["id"] for u in cat["units"])
    # по умолчанию «с» — с вечера дня выезда, «по» — до утра дня заезда
    r = _ooo(manager_client, u1, "2040-03-10", "2040-03-14")
    assert r.status_code == 200, r.text
    o = r.json()["result"]
    assert (o["start_half"], o["end_half"], o["version"], o["reason"]) == ("PM", "AM", 1, "Ремонт")
    # выезд утром 10.03 и OOO с вечера того же дня — не конфликт; заезд вечером 14.03 — тоже
    out = create_res(manager_client, cat, "2040-03-08", "2040-03-10")
    inn = create_res(manager_client, cat, "2040-03-14", "2040-03-16")
    assert units_of(out) == [u1] and units_of(inn) == [u1]
    # «с утра» и «до вечера» — сутки целиком: обе брони уходят из объекта
    full = manager_client.put(f"{API}/ooo/{o['id']}", json={**{k: o[k] for k in ("unit_id", "start", "end", "reason")},
                                                            "start_half": "AM", "end_half": "PM", "version": 1})
    assert full.status_code == 200, full.text
    assert full.json()["result"]["version"] == 2
    assert {x["reservation_id"] for x in full.json()["diff"]["moved"]} == {out["id"], inn["id"]}
    # одни сутки — только «с утра» + «до вечера»
    bad = _ooo(manager_client, u2, "2040-03-20", "2040-03-20")
    assert bad.status_code == 422, bad.text
    ok = _ooo(manager_client, u2, "2040-03-20", "2040-03-20", start_half="AM", end_half="PM")
    assert ok.status_code == 200, ok.text
    assert _ooo(manager_client, u2, "2040-03-25", "2040-03-24").status_code == 422
    gone = manager_client.delete(f"{API}/ooo/{o['id']}", params={"version": 2})
    assert gone.status_code == 200 and gone.json()["result"] == {"id": o["id"], "deleted": True}
    assert manager_client.delete(f"{API}/ooo/{o['id']}", params={"version": 2}).status_code == 404
    assert units_of(manager_client.get(f"{API}/reservations/{out['id']}").json()) == [u1]


def test_ooo_absent_unit_422(manager_role_client, manager_client, today):
    today("2041-03-01")
    cat = make_category(manager_role_client, n_units=2)
    gone = cat["units"][1]
    _version(manager_role_client, "2041-03-10", ("DELETE", f"units/{gone['id']}", {}))
    assert _ooo(manager_client, gone["id"], "2041-03-05", "2041-03-09").status_code == 200
    r = _ooo(manager_client, gone["id"], "2041-03-08", "2041-03-14")
    assert r.status_code == 422
    assert r.json()["detail"] == f"объекта {gone['label']} нет в фонде 10.03–14.03"
    assert _ooo(manager_client, 10 ** 9, "2041-03-08", "2041-03-14").status_code == 422     # объекта нет вовсе


def test_ooo_overlap_409(manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=2)
    u1, u2 = (u["id"] for u in cat["units"])
    a = _ooo(manager_client, u1, "2040-04-10", "2040-04-14").json()["result"]
    assert _ooo(manager_client, u1, "2040-04-12", "2040-04-16").status_code == 409
    assert _ooo(manager_client, u2, "2040-04-12", "2040-04-16").status_code == 200     # другой объект
    # стык: первое заканчивается утром 14.04, второе начинается вечером 14.04 — не пересечение
    assert _ooo(manager_client, u1, "2040-04-14", "2040-04-18").status_code == 200
    # утро 14.04 — пересечение с первым (оно занимает его по 14.04 AM включительно)
    assert _ooo(manager_client, u1, "2040-04-14", "2040-04-18", start_half="AM").status_code == 409
    # правка не конфликтует сама с собой
    same = manager_client.put(f"{API}/ooo/{a['id']}", json={"unit_id": u1, "start": "2040-04-10", "end": "2040-04-14",
                                                            "reason": "иначе", "version": 1})
    assert same.status_code == 200, same.text


def test_version_conflict_409(manager_role_client, manager_client, db):
    cat = make_category(manager_role_client, n_units=1)
    u1 = cat["units"][0]["id"]
    o = _ooo(manager_client, u1, "2040-05-10", "2040-05-12").json()["result"]
    body = {"unit_id": u1, "start": "2040-05-10", "end": "2040-05-13", "reason": "x", "version": o["version"]}
    assert manager_client.put(f"{API}/ooo/{o['id']}", json=body).status_code == 200
    stale = manager_client.put(f"{API}/ooo/{o['id']}", json=body)
    assert stale.status_code == 409
    assert manager_client.delete(f"{API}/ooo/{o['id']}", params={"version": 1}).status_code == 409
    before = dump(db)
    assert manager_client.delete(f"{API}/ooo/{o['id']}", params={"version": 1, "preview": 1}).status_code == 409
    assert dump(db) == before


def test_past_edits_allowed_and_audited(manager_role_client, manager_client, db, today):
    today("2040-05-20")
    cat = make_category(manager_role_client, n_units=1)
    u1 = cat["units"][0]["id"]
    today("2040-06-20")
    o = _ooo(manager_client, u1, "2040-06-01", "2040-06-05").json()["result"]       # целиком в прошлом
    r = manager_client.put(f"{API}/ooo/{o['id']}", json={"unit_id": u1, "start": "2040-06-02", "end": "2040-06-08",
                                                         "start_half": "AM", "reason": "дольше", "version": 1})
    assert r.status_code == 200, r.text
    assert manager_client.delete(f"{API}/ooo/{o['id']}", params={"version": 2}).status_code == 200
    rows = db.scalars(select(AuditLog).where(AuditLog.action == "stays_ooo", AuditLog.target == f"ooo:{o['id']}")
                      .order_by(AuditLog.id)).all()
    diffs = [json.loads(x.payload_json)["diff"] for x in rows]
    assert len(diffs) == 3
    assert diffs[0]["start"] == [None, "2040-06-01"]
    assert diffs[1] == {"start": ["2040-06-01", "2040-06-02"], "end": ["2040-06-05", "2040-06-08"],
                        "start_half": ["PM", "AM"], "reason": ["Ремонт", "дольше"], "version": [1, 2]}
    assert diffs[2]["start"] == ["2040-06-02", None]


def test_ooo_preview_equals_save(manager_role_client, manager_client, db):
    cat = make_category(manager_role_client, n_units=1)
    u1 = cat["units"][0]["id"]
    create_res(manager_client, cat, "2040-07-10", "2040-07-14")
    body = {"unit_id": u1, "start": "2040-07-11", "end": "2040-07-12", "start_half": "AM", "end_half": "PM",
            "reason": "Покраска"}
    before = dump(db)
    pv = manager_client.post(f"{API}/ooo", params={"preview": 1}, json=body)
    assert pv.status_code == 200 and dump(db) == before
    sv = manager_client.post(f"{API}/ooo", json=body)
    assert pv.json()["diff"] == sv.json()["diff"]
    assert [w["kind"] for w in sv.json()["diff"]["warnings_added"] if w["day"] is None] == ["overbooked"]


def test_lists_filters_sort(manager_role_client, manager_client):
    a = make_category(manager_role_client, n_units=2)
    b = make_category(manager_role_client, n_units=1)
    ids = {}
    for key, cat, i, s, e, why in (("a1", a, 0, "2042-01-10", "2042-01-12", "Ремонт ванной"),
                                   ("a2", a, 1, "2042-01-20", "2042-01-22", "Покраска"),
                                   ("b1", b, 0, "2042-02-01", "2042-02-03", "ремонт кровли")):
        ids[key] = _ooo(manager_client, cat["units"][i]["id"], s, e, why).json()["result"]["id"]

    def rows(**p):
        r = manager_client.get(f"{API}/ooo", params={"first": "2042-01-01", "last": "2042-12-31", **p})
        assert r.status_code == 200, r.text
        return [x["id"] for x in r.json()["rows"]]
    assert rows(category_ids=a["id"]) == [ids["a1"], ids["a2"]]
    assert rows(category_ids=[a["id"], b["id"]], sort="start", dir="desc") == [ids["b1"], ids["a2"], ids["a1"]]
    assert rows(category_ids=[a["id"], b["id"]], q="РЕМОНТ") == [ids["a1"], ids["b1"]]
    assert rows(category_ids=[a["id"], b["id"]], first="2042-01-15", last="2042-01-31") == [ids["a2"]]
    assert rows(category_ids=[a["id"], b["id"]], sort="reason") == [ids["a2"], ids["a1"], ids["b1"]]
    paged = manager_client.get(f"{API}/ooo", params={"category_ids": [a["id"], b["id"]], "limit": 1, "offset": 1}).json()
    assert paged["total"] == 3 and [x["id"] for x in paged["rows"]] == [ids["a2"]]
    row = manager_client.get(f"{API}/ooo", params={"category_ids": b["id"]}).json()["rows"][0]
    assert (row["unit"], row["category"], row["start_half"], row["end_half"], row["reason"]) == (
        b["units"][0]["label"], b["code"], "PM", "AM", "ремонт кровли")
    assert row["author"]
    assert manager_client.get(f"{API}/ooo", params={"sort": "nope"}).status_code == 422
    assert manager_client.get(f"{API}/ooo", params={"first": "2042-01-01"}).status_code == 422
    assert manager_client.get(f"{API}/ooo", params={"building": 1}).status_code == 422


def test_visible_to_all_levels_with_titles(manager_role_client, manager_client, mgmt_client, occupancy_client,
                                           employee_client):
    cat = make_category(manager_role_client, n_units=1)
    o = _ooo(manager_client, cat["units"][0]["id"], "2043-01-10", "2043-01-12", "Замена окон").json()["result"]
    for c in (manager_client, mgmt_client, occupancy_client):
        r = c.get(f"{API}/ooo", params={"category_ids": cat["id"]})
        assert r.status_code == 200, r.text
        assert [(x["id"], x["reason"]) for x in r.json()["rows"]] == [(o["id"], "Замена окон")]
    assert employee_client.get(f"{API}/ooo").status_code == 403
    # писать — только stays.edit
    for c in (mgmt_client, occupancy_client):
        assert _ooo(c, cat["units"][0]["id"], "2043-02-10", "2043-02-12").status_code == 403
