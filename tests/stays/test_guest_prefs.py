"""Шахматка, часть 2, задача 5: пожелания гостя к объекту (§5) — API и права, выбор объекта по
пожеланиям главного гостя (узел, флаг по версии фонда дня, объект и его наследник по lineage),
статус на карточке брони, перенос при объединении гостей."""
from __future__ import annotations

from sqlalchemy import select

from app.core.audit import AuditLog

from .helpers import API, FundDraft, create_res, make_category, make_guest, uniq, units_of
from .test_allocation_versions import _version

MAIN = "main"


def _put(c, gid, prefs):
    return c.put(f"{API}/guests/{gid}/prefs", json={"prefs": prefs})


def _book(c, cat, guest, ci, co):
    return create_res(c, cat, ci, co, [(guest["id"], MAIN, None, None)])


def test_prefs_crud_and_perm(manager_role_client, manager_client, names_client, occupancy_client, client, db):
    cat = make_category(manager_role_client, n_units=2)
    uid = cat["units"][1]["id"]
    g = make_guest(manager_client)
    assert manager_client.get(f"{API}/guests/{g['id']}/prefs").json() == []
    r = _put(manager_client, g["id"], [{"kind": "unit", "ref_id": uid, "priority": 5}])
    assert r.status_code == 200, r.text
    assert r.json() == [{"kind": "unit", "ref_id": uid, "priority": 5, "title": cat["units"][1]["label"]}]
    assert manager_client.get(f"{API}/guests/{g['id']}/prefs").json() == r.json()
    # замена целиком, главные — первыми
    title = "пж-флаг-" + uniq()
    flag = manager_role_client.post(f"{API}/fund/flags", json={"title": title}).json()
    r = _put(manager_client, g["id"], [{"kind": "flag", "ref_id": flag["id"], "priority": 1},
                                       {"kind": "unit", "ref_id": uid, "priority": 3}])
    assert [p["kind"] for p in r.json()] == ["unit", "flag"] and r.json()[1]["title"] == title
    assert _put(manager_client, g["id"], []).json() == []
    # ввод — 422, гость — 404
    bad = [[{"kind": "color", "ref_id": 1, "priority": 1}], [{"kind": "unit", "ref_id": uid, "priority": 0}],
           [{"kind": "unit", "ref_id": uid, "priority": 1}, {"kind": "unit", "ref_id": uid, "priority": 2}],
           [{"kind": "unit", "ref_id": 99999999, "priority": 1}], [{"kind": "group", "ref_id": 99999999, "priority": 1}],
           [{"kind": "flag", "ref_id": 99999999, "priority": 1}]]
    assert [_put(manager_client, g["id"], b).status_code for b in bad] == [422] * len(bad)
    assert _put(manager_client, 99999999, []).status_code == 404
    # права: «с фамилиями», загрузка и аноним — без доступа
    for c, code in ((names_client, 403), (occupancy_client, 403), (client, 401)):
        assert c.get(f"{API}/guests/{g['id']}/prefs").status_code == code
        assert _put(c, g["id"], []).status_code == code
    rows = db.scalars(select(AuditLog).where(AuditLog.action == "stays_guest_prefs",
                                             AuditLog.target == f"guest:{g['id']}")).all()
    assert len(rows) == 3


def test_pref_satisfied_when_free(manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=3)
    want = cat["units"][2]["id"]
    g = make_guest(manager_client)
    plain = _book(manager_client, cat, make_guest(manager_client), "2048-03-10", "2048-03-14")
    assert units_of(plain) == [cat["units"][0]["id"]]                # без пожеланий — по порядку
    assert _put(manager_client, g["id"], [{"kind": "unit", "ref_id": want, "priority": 1}]).status_code == 200
    r = _book(manager_client, cat, g, "2048-03-10", "2048-03-14")
    assert units_of(r) == [want]
    card = manager_client.get(f"{API}/reservations/{r['id']}/card").json()
    assert card["pref"] == {"met": True, "title": "пожелание выполнено"}


def test_pref_ignored_when_busy(manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=2)
    first, want = (u["id"] for u in cat["units"])
    g = make_guest(manager_client)
    _put(manager_client, g["id"], [{"kind": "unit", "ref_id": want, "priority": 1}])
    a = _book(manager_client, cat, g, "2048-04-10", "2048-04-14")
    b = _book(manager_client, cat, g, "2048-04-12", "2048-04-16")
    assert units_of(a) == [want] and units_of(b) == [first]          # занято — мягко, без овербукинга
    card = manager_client.get(f"{API}/reservations/{b['id']}/card").json()
    assert card["pref"] == {"met": False, "title": "пожелание не выполнено"}


def test_pref_group_and_priority_sum(manager_role_client, manager_client):
    d = FundDraft(manager_role_client)
    grp = d.call("POST", "groups", title="Линия " + uniq())["id"]
    d.publish()
    cat = make_category(manager_role_client, n_units=3, group_id=grp)
    other = make_category(manager_role_client, n_units=1)
    b = cat["units"][1]["id"]
    g = make_guest(manager_client)
    # группа даёт всем трём объектам один счёт, объект b — больше
    _put(manager_client, g["id"], [{"kind": "group", "ref_id": grp, "priority": 2},
                                   {"kind": "unit", "ref_id": b, "priority": 1}])
    assert units_of(_book(manager_client, cat, g, "2048-05-10", "2048-05-12")) == [b]
    # узел — проверка, что объект вне ветки не выигрывает: категория без группы остаётся по порядку
    assert units_of(_book(manager_client, other, g, "2048-05-10", "2048-05-12")) == [other["units"][0]["id"]]


def test_pref_flag_by_version_day(manager_role_client, manager_client, today):
    today("2048-06-01")
    cat = make_category(manager_role_client, n_units=2)
    first, second = (u["id"] for u in cat["units"])
    flag = manager_role_client.post(f"{API}/fund/flags", json={"title": "пж-флаг-" + uniq()}).json()["id"]
    _version(manager_role_client, "2048-06-10", ("PUT", "flags", {"flag_id": flag, "unit_ids": [second], "value": True}))
    g = make_guest(manager_client)
    _put(manager_client, g["id"], [{"kind": "flag", "ref_id": flag, "priority": 1}])
    before = _book(manager_client, cat, g, "2048-06-04", "2048-06-08")     # флага в этой версии ещё нет
    after = _book(manager_client, cat, g, "2048-06-12", "2048-06-15")
    assert units_of(before) == [first] and units_of(after) == [second]


def test_pref_unit_follows_lineage(manager_role_client, manager_client, today):
    today("2048-07-01")
    cat = make_category(manager_role_client, n_units=2)
    plain, whole = (u["id"] for u in cat["units"])
    g = make_guest(manager_client)
    _put(manager_client, g["id"], [{"kind": "unit", "ref_id": whole, "priority": 1}])
    assert units_of(_book(manager_client, cat, g, "2048-07-05", "2048-07-08")) == [whole]
    _version(manager_role_client, "2048-07-10", ("POST", f"units/{whole}/split",
                                                 {"parts": [{"label": cat["code"] + "-2a"}, {"label": cat["code"] + "-2b"}]}))
    r = _book(manager_client, cat, g, "2048-07-12", "2048-07-15")
    got = units_of(r)[0]
    assert got not in (plain, whole)                                      # наследник делённого, а не первый по порядку
    snap = manager_client.get(f"{API}/fund/snapshot", params={"date": "2048-07-12"}).json()
    heirs = {u["id"] for u in snap["units"] if u["label"].startswith(cat["code"] + "-2")}
    assert len(heirs) == 2 and got in heirs


def test_card_shows_pref_status(manager_role_client, manager_client, names_client):
    cat = make_category(manager_role_client, n_units=2)
    want = cat["units"][1]["id"]
    g, h = make_guest(manager_client), make_guest(manager_client)
    _put(manager_client, g["id"], [{"kind": "unit", "ref_id": want, "priority": 1}])
    mine = _book(manager_client, cat, g, "2048-08-10", "2048-08-12")
    second = create_res(manager_client, cat, "2048-08-10", "2048-08-12", [(h["id"], MAIN, None, None), (g["id"], "guest", None, None)])
    for rid, met in ((mine["id"], True), (second["id"], None)):
        for c in (manager_client, names_client):                     # статус виден и на уровне «с фамилиями»
            card = c.get(f"{API}/reservations/{rid}/card").json()
            assert (card["pref"] or {}).get("met") is met
    # пожелания только главного: у брони, где g не главный, статуса нет
    assert "пожелани" not in str(names_client.get(f"{API}/reservations/{mine['id']}/card").json()["occupants"])


def test_merge_moves_prefs_without_duplicates(manager_role_client, manager_client):
    cat = make_category(manager_role_client, n_units=2)
    u1, u2 = (u["id"] for u in cat["units"])
    flag = manager_role_client.post(f"{API}/fund/flags", json={"title": "пж-флаг-" + uniq()}).json()["id"]
    keep, drop = make_guest(manager_client), make_guest(manager_client)
    _put(manager_client, keep["id"], [{"kind": "unit", "ref_id": u1, "priority": 5}])
    _put(manager_client, drop["id"], [{"kind": "unit", "ref_id": u1, "priority": 9},
                                      {"kind": "unit", "ref_id": u2, "priority": 4},
                                      {"kind": "flag", "ref_id": flag, "priority": 3}])
    r = manager_client.post(f"{API}/guests/merge", json={"keep_id": keep["id"], "drop_id": drop["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["moves"]["prefs"] == 2
    got = {(p["kind"], p["ref_id"]): p["priority"] for p in manager_client.get(f"{API}/guests/{keep['id']}/prefs").json()}
    assert got == {("unit", u1): 5, ("unit", u2): 4, ("flag", flag): 3}
