"""Часть 4, задача 3: что батлер правит у своих гостей — профиль (свободные поля), семейное дерево и
прочие связи (новый человек становится «своим»), пожелания к объекту с предпросмотром; состав брони —
родственник по дереву (в том числе вычисленный) или прямая связь (спецификация
2026-10-27-stays-butler-mine-design §3, §7)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select

from app.modules.stays.adapters.orm import Guest
from app.modules.stays.application import mine

from .helpers import API, create_res, make_category, make_code, make_guest, units_of
from .test_mine_ownership import _guest_body, _line, ivanov_grant, stay  # noqa: F401 — фикстуры
from .test_occupancy_and_mine import _body, _doc


def _link(c, a: int, b: int, kind: str, **kw):
    return c.post(f"{API}/guests/{a}/links", json={"guest_id": b, "kind": kind, **kw})


def _new(c, gid: int, kind: str = "parent", last: str = "Новенький", **kw):
    return c.post(f"{API}/guests/{gid}/links", json={"new_guest": {"last_name": last, "first_name": "Сын",
                                                                    "gender": "m"}, "kind": kind, **kw})


def _own(stay, butlers, ci: int = 80, co: int = 82, n: int = 1) -> dict:
    r = stay(ci, co, n_guests=n)
    _line(butlers["a"], r["first"], r["id"])
    return r


def _foreign(stay, butlers, ci: int = 80, co: int = 82) -> dict:
    r = stay(ci, co)
    _line(butlers["b"], r["first"], r["id"])
    return r


def _named(db, last: str) -> int:
    return db.scalar(select(func.count()).select_from(Guest).where(Guest.last_name == last))


# ── семейное дерево и связи ──

def test_mine_adds_child_new_person_becomes_own(stay, butlers, butler_client, manager_client, db):
    gid = _own(stay, butlers)["guests"][0]
    r = _new(butler_client, gid, last="Сынов")
    assert r.status_code == 200, r.text
    child = r.json()["guest_id"]
    db.expire_all()
    assert db.get(Guest, child).created_by_employee_id == butlers["a"]
    assert mine.owns_guest(db, butlers["a"], child) and not mine.owns_guest(db, butlers["b"], child)
    fam = butler_client.get(f"{API}/guests/{gid}/family").json()
    assert [gid, child] in [[ln["a"], ln["b"]] for ln in fam["links"] if ln["kind"] == "parent"]
    card = butler_client.get(f"{API}/guests/{child}/card")
    assert card.status_code == 200 and card.json()["last_name"] == "Сынов"
    # профиль заведённого им человека батлер правит
    resp = butler_client.put(f"{API}/guests/{child}", json=_guest_body(card.json(), note="сын гостя",
                                                                         gender=card.json()["gender"]))
    assert resp.status_code == 200, resp.text
    # новый человек от старшего — без отметки батлера
    other = _new(manager_client, gid, last="Дочкин").json()["guest_id"]
    db.expire_all()
    assert db.get(Guest, other).created_by_employee_id is None


def test_mine_link_on_foreign_guest_403(stay, butlers, butler_client, manager_client, db):
    gid = _foreign(stay, butlers)["guests"][0]
    stranger = make_guest(manager_client)
    assert _new(butler_client, gid, last="Чужедет").status_code == 403
    assert _named(db, "Чужедет") == 0
    assert _link(butler_client, gid, stranger["id"], "assistant").status_code == 403
    assert manager_client.get(f"{API}/guests/{gid}").json()["links"] == []


def test_mine_link_delete_ownership(stay, butlers, butler_client, manager_client):
    """Удалить связь или отметить «бывшие» — если хотя бы одна сторона своя."""
    own = _own(stay, butlers)["guests"][0]
    f1, f2 = _foreign(stay, butlers)["guests"][0], _foreign(stay, butlers)["guests"][0]
    alien = _link(manager_client, f1, f2, "spouse").json()["id"]
    mixed = _link(manager_client, own, f1, "assistant").json()["id"]
    spouse = _link(manager_client, f2, own, "spouse", former=True).json()["id"]
    assert butler_client.delete(f"{API}/guest-links/{alien}").status_code == 403
    assert butler_client.patch(f"{API}/guest-links/{alien}", json={"former": True}).status_code == 403
    assert {x["id"] for x in manager_client.get(f"{API}/guests/{f1}").json()["links"]} == {alien, mixed}
    assert butler_client.patch(f"{API}/guest-links/{spouse}", json={"former": True}).status_code == 200
    assert butler_client.delete(f"{API}/guest-links/{mixed}").status_code == 200
    assert butler_client.delete(f"{API}/guest-links/{spouse}").status_code == 200
    assert [x["id"] for x in manager_client.get(f"{API}/guests/{f1}").json()["links"]] == [alien]


def test_mine_tree_checks_422(stay, butlers, butler_client, db):
    """Проверки дерева у батлера те же: свой предок, третий родитель — 422, ничего не создаётся."""
    gid = _own(stay, butlers)["guests"][0]
    child = _new(butler_client, gid).json()["guest_id"]
    r = _link(butler_client, gid, child, "parent", other_is_parent=True)
    assert r.status_code == 422 and "своим предком" in r.json()["detail"]
    for last in ("Отцов", "Матерева"):
        assert _new(butler_client, gid, last=last, other_is_parent=True).status_code == 200
    r = _new(butler_client, gid, last="Третьев", other_is_parent=True)
    assert r.status_code == 422 and r.json()["detail"] == "У ребёнка не больше двух родителей"
    assert _named(db, "Третьев") == 0


# ── пожелания к объекту ──

def _prefs(c, gid: int, prefs: list, **params):
    return c.put(f"{API}/guests/{gid}/prefs", json={"prefs": prefs}, params=params)


def test_mine_prefs_preview_equals_save(manager_role_client, manager_client, butlers, butler_client, db):
    from .test_preview import dump

    cat = make_category(manager_role_client, n_units=2)
    first, want = (u["id"] for u in cat["units"])
    g = make_guest(manager_client)
    r = create_res(manager_client, cat, "2049-03-10", "2049-03-14", [(g["id"], "main", None, None)])
    assert units_of(r) == [first]
    _line(butlers["a"], dt.date(2049, 3, 11), r["id"])
    assert butler_client.get(f"{API}/guests/{g['id']}/prefs").json() == []
    prefs = [{"kind": "unit", "ref_id": want, "priority": 1}]
    before = dump(db)
    pv = _prefs(butler_client, g["id"], prefs, preview=1)
    assert pv.status_code == 200, pv.text
    pv = pv.json()
    assert pv["preview"] is True and dump(db) == before
    assert [(m["reservation_id"], m["from_unit"], m["to_unit"]) for m in pv["diff"]["moved"]] == [(r["id"], first, want)]
    sv = _prefs(butler_client, g["id"], prefs).json()
    assert sv["preview"] is False and sv["result"] == pv["result"] and sv["diff"] == pv["diff"]
    assert [p["ref_id"] for p in butler_client.get(f"{API}/guests/{g['id']}/prefs").json()] == [want]


def test_mine_prefs_new_overbook_409(manager_role_client, manager_client, butlers, butler_client):
    """Пожелание уводит гостя в объект, нужный другой брони: у батлера нет stays.overbook — 409."""
    cat = make_category(manager_role_client, n_units=2)
    u1, u2 = (u["id"] for u in cat["units"])
    assert manager_client.post(f"{API}/ooo", json={"unit_id": u1, "start": "2049-04-12", "end": "2049-04-14",
                                                   "start_half": "AM", "end_half": "PM"}).status_code == 200
    g = make_guest(manager_client)
    a = create_res(manager_client, cat, "2049-04-09", "2049-04-11", [(g["id"], "main", None, None)])
    d = create_res(manager_client, cat, "2049-04-10", "2049-04-13")
    assert units_of(a) == [u1] and units_of(d) == [u2]
    _line(butlers["a"], dt.date(2049, 4, 9), a["id"])
    prefs = [{"kind": "unit", "ref_id": u2, "priority": 1}]
    r = _prefs(butler_client, g["id"], prefs)
    assert r.status_code == 409 and r.json()["detail"]["overbook"] is True
    pv = _prefs(butler_client, g["id"], prefs, preview=1)
    assert pv.status_code == 200 and "overbook_refused" in pv.json()
    assert manager_client.get(f"{API}/guests/{g['id']}/prefs").json() == []


def test_mine_prefs_foreign_guest_403(stay, butlers, butler_client, manager_client):
    gid = _foreign(stay, butlers)["guests"][0]
    assert butler_client.get(f"{API}/guests/{gid}/prefs").status_code == 403
    assert _prefs(butler_client, gid, []).status_code == 403
    assert _prefs(butler_client, gid, [], preview=1).status_code == 403
    assert _prefs(butler_client, 99999999, []).status_code == 404


# ── состав брони ──

def _add_occupant(c, rid: int, gid: int):
    doc = _doc(c, rid)
    occ = doc["occupants"] + [{"guest_id": gid, "role": "guest", "date_from": doc["check_in"],
                               "date_to": doc["check_out"]}]
    return c.put(f"{API}/reservations/{rid}", json=_body(doc, occupants=occ))


def test_mine_adds_computed_relative(stay, butlers, butler_client, manager_client):
    """Бабушка жены главного гостя — вычисленная родня (через дерево), прямой связи с проживающим нет."""
    r = _own(stay, butlers)
    husband = r["guests"][0]
    wife, mother, granny = (make_guest(manager_client)["id"] for _ in range(3))
    assert _link(manager_client, husband, wife, "spouse").status_code == 200
    assert _link(manager_client, mother, wife, "parent").status_code == 200
    assert _link(manager_client, granny, mother, "parent").status_code == 200
    resp = _add_occupant(butler_client, r["id"], granny)
    assert resp.status_code == 200, resp.text
    assert granny in {o["guest_id"] for o in _doc(butler_client, r["id"])["occupants"]}
    # внук жены — тоже (через жену, которой в брони нет)
    child = _new(manager_client, wife, last="Детков").json()["guest_id"]
    grandson = _new(manager_client, child, last="Внуков").json()["guest_id"]
    assert _add_occupant(butler_client, r["id"], grandson).status_code == 200


def test_mine_adds_direct_link_assistant(stay, butlers, butler_client, manager_client):
    r = _own(stay, butlers)
    helper = make_guest(manager_client)["id"]
    assert _link(manager_client, r["guests"][0], helper, "assistant").status_code == 200
    resp = _add_occupant(butler_client, r["id"], helper)
    assert resp.status_code == 200, resp.text


def test_mine_adds_unlinked_403(stay, butlers, butler_client, manager_client):
    r = _own(stay, butlers)
    stranger = make_guest(manager_client)["id"]
    # родня чужого человека, не проживающего в брони, — тоже нет
    _link(manager_client, make_guest(manager_client)["id"], stranger, "parent")
    resp = _add_occupant(butler_client, r["id"], stranger)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Батлер добавляет только родственников и связанных с проживающими брони"
    assert butler_client.get(f"{API}/guests/{stranger}").status_code == 403


# ── профиль ──

def test_mine_profile_locked_fields_403(stay, butlers, butler_client, manager_role_client):
    gid = _own(stay, butlers)["guests"][0]
    card = butler_client.get(f"{API}/guests/{gid}").json()
    code = make_code(manager_role_client)
    locked = {"special": True, "vip_code_id": code["id"], "last_name": "Другов", "first_name": "Пётр",
              "middle_name": "Ильич", "phone": "+79991234567", "email": "x@example.com", "birth_date": "1980-01-02",
              "gender": "f"}
    for k, v in locked.items():
        r = butler_client.put(f"{API}/guests/{gid}", json=_guest_body(card, **{k: v}))
        assert r.status_code == 403, (k, r.text)
    free = {"preferences": {"pillow": "пух"}, "special_dates": [{"date": "2049-05-01", "what": "годовщина"}],
            "note": "любит тишину"}
    r = butler_client.put(f"{API}/guests/{gid}", json=_guest_body(card, **free))
    assert r.status_code == 200, r.text
    after = butler_client.get(f"{API}/guests/{gid}").json()
    assert after["note"] == "любит тишину" and after["special"] is False and after["last_name"] == card["last_name"]


def test_no_guest_edit_perm_read_only(stay, butlers, butler_client, manager_client, ivanov_grant):  # noqa: F811
    """Снятое stays.mine_guest_edit: профиль, дерево и пожелания своего гостя — только чтение."""
    gid = _own(stay, butlers)["guests"][0]
    other = make_guest(manager_client)["id"]
    link = _link(manager_client, gid, other, "spouse").json()["id"]
    ivanov_grant("stays.mine_guest_edit")
    for url in (f"/guests/{gid}", f"/guests/{gid}/card", f"/guests/{gid}/prefs", f"/guests/{gid}/family"):
        assert butler_client.get(API + url).status_code == 200, url
    card = butler_client.get(f"{API}/guests/{gid}").json()
    assert butler_client.put(f"{API}/guests/{gid}", json=_guest_body(card, note="нет")).status_code == 403
    assert _new(butler_client, gid).status_code == 403
    assert butler_client.patch(f"{API}/guest-links/{link}", json={"former": True}).status_code == 403
    assert butler_client.delete(f"{API}/guest-links/{link}").status_code == 403
    assert _prefs(butler_client, gid, []).status_code == 403


# ── доработка 1: вторая сторона связи от батлера — своя или новый человек ──

def test_mine_link_to_foreign_existing_403(stay, butlers, butler_client, manager_client, db):
    """Связь своего гостя с чужим существующим — 403, ничего не создано: иначе через состав брони
    батлер открыл бы себе чужой профиль."""
    r = _own(stay, butlers)
    own = r["guests"][0]
    foreign = _foreign(stay, butlers)["guests"][0]
    resp = _link(butler_client, own, foreign, "assistant")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Связать можно только со своим гостем или новым человеком"
    assert manager_client.get(f"{API}/guests/{own}").json()["links"] == []
    assert _add_occupant(butler_client, r["id"], foreign).status_code == 403
    assert butler_client.get(f"{API}/guests/{foreign}").status_code == 403


def test_mine_new_child_with_foreign_second_parent_403(stay, butlers, butler_client, manager_client, db):
    own = _own(stay, butlers)["guests"][0]
    foreign = _foreign(stay, butlers)["guests"][0]
    resp = _new(butler_client, own, last="Полусиротов", also_parent_id=foreign)
    assert resp.status_code == 403
    assert _named(db, "Полусиротов") == 0
    assert manager_client.get(f"{API}/guests/{own}").json()["links"] == []
    assert manager_client.get(f"{API}/guests/{foreign}").json()["links"] == []


def test_mine_link_own_to_own_existing_200(stay, butlers, butler_client):
    r = _own(stay, butlers, n=2)
    a, b = r["guests"]
    assert _link(butler_client, a, b, "spouse").status_code == 200
    spouse = _new(butler_client, a, last="Общедетов", also_parent_id=b)
    assert spouse.status_code == 200, spouse.text
    assert len(spouse.json()["ids"]) == 2


def test_mine_guest_search_only_own(stay, butlers, butler_client, manager_client):
    own = _own(stay, butlers)["guests"][0]
    foreign = _foreign(stay, butlers)["guests"][0]
    last = "Искомов" + str(own)
    for gid in (own, foreign):
        manager_client.put(f"{API}/guests/{gid}", json={**_guest_body(manager_client.get(f"{API}/guests/{gid}").json()),
                                                         "last_name": last})
    every = {g["id"] for g in butler_client.get(f"{API}/guests", params={"q": last}).json()}
    mine_only = {g["id"] for g in butler_client.get(f"{API}/guests", params={"q": last, "mine": 1}).json()}
    assert {own, foreign} <= every and mine_only == {own}


# ── доработка 3: через бывшего супруга — только он сам ──

def test_mine_former_spouse_relatives_not_kin(stay, butlers, butler_client, manager_client):
    r = _own(stay, butlers)
    husband = r["guests"][0]
    ex, ex_mother = (make_guest(manager_client)["id"] for _ in range(2))
    assert _link(manager_client, husband, ex, "spouse", former=True).status_code == 200
    assert _link(manager_client, ex_mother, ex, "parent").status_code == 200
    resp = _add_occupant(butler_client, r["id"], ex_mother)
    assert resp.status_code == 403, resp.text
    assert _add_occupant(butler_client, r["id"], ex).status_code == 200
