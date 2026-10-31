"""Шахматка, задача 7: профили гостей, связи «кто кому», поиск, видимость полей."""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select

from app.core.audit import AuditLog
from app.modules.stays.application.guests import format_phone, normalize_phone

API = "/api/stays"


def _uniq() -> str:
    return uuid.uuid4().hex[:6]


def _guest(c, last="Орлов", **kw):
    r = c.post(f"{API}/guests", json={"last_name": last, "first_name": "Андрей", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_normalize_phone():
    assert normalize_phone("8 (916) 123-45-67") == "+79161234567"
    assert normalize_phone("9161234567") == "+79161234567"
    assert normalize_phone("+44 20 7946 0958") == "+442079460958"
    assert normalize_phone("") == ""
    assert format_phone("+79161234567") == "+7 916 123-45-67"


def test_bad_phone_refused(manager_client):
    r = manager_client.post(f"{API}/guests", json={"last_name": "Икс", "phone": "12"})
    assert r.status_code == 422 and r.json()["detail"] == "Телефон должен быть в формате +7 999 123-45-67"


def test_phone_normalized_on_save(manager_client):
    g = _guest(manager_client, phone="8 (916) 123-45-67")
    assert g["phone"] == "+79161234567"


def test_level_validated(manager_client):
    r = manager_client.post(f"{API}/guests", json={"last_name": "Икс", "level": "gold"})
    assert r.status_code == 422


def test_link_labels_both_sides(manager_client):
    parent = _guest(manager_client, "Родитель" + _uniq(), gender="f")
    child = _guest(manager_client, "Ребёнок" + _uniq())
    r = manager_client.post(f"{API}/guests/{parent['id']}/links", json={"guest_id": child["id"], "kind": "parent"})
    assert r.status_code == 200, r.text
    a = manager_client.get(f"{API}/guests/{parent['id']}").json()["links"]
    b = manager_client.get(f"{API}/guests/{child['id']}").json()["links"]
    assert [(x["guest_id"], x["label"]) for x in a] == [(child["id"], "ребёнок")]
    assert [(x["guest_id"], x["label"]) for x in b] == [(parent["id"], "мать")]
    assert manager_client.delete(f"{API}/guest-links/{a[0]['id']}").status_code == 200
    assert manager_client.get(f"{API}/guests/{parent['id']}").json()["links"] == []


def test_link_to_self_refused(manager_client):
    g = _guest(manager_client)
    r = manager_client.post(f"{API}/guests/{g['id']}/links", json={"guest_id": g["id"], "kind": "spouse"})
    assert r.status_code == 422 and r.json()["detail"] == "Гость не может быть связан сам с собой"


def test_duplicate_link_refused(manager_client):
    a, b = _guest(manager_client), _guest(manager_client)
    body = {"guest_id": b["id"], "kind": "spouse"}
    assert manager_client.post(f"{API}/guests/{a['id']}/links", json=body).status_code == 200
    r = manager_client.post(f"{API}/guests/{a['id']}/links", json=body)
    assert r.status_code == 409 and r.json()["detail"] == "Такая связь уже есть"


def test_search_cyrillic_case_insensitive(manager_client):
    last = "Ёлкина" + _uniq()
    g = _guest(manager_client, last)
    found = manager_client.get(f"{API}/guests", params={"q": last.lower()}).json()
    assert [x["id"] for x in found] == [g["id"]]


def test_search_by_phone_digits(manager_client):
    g = _guest(manager_client, "Телефонов" + _uniq(), phone="+7 903 555-12-34")
    found = manager_client.get(f"{API}/guests", params={"q": "8 903 555"}).json()
    assert g["id"] in [x["id"] for x in found]


def test_search_by_searchable_field_only(manager_role_client, manager_client):
    u = _uniq()
    for code, searchable in ((f"club{u}", True), (f"secret{u}", False)):
        r = manager_role_client.post(f"{API}/fields", json={
            "target": "guest", "code": code, "title": code, "kind": "text", "searchable": searchable})
        assert r.status_code == 200, r.text
    g = _guest(manager_client, fields={f"club{u}": f"gold{u}", f"secret{u}": f"hidden{u}"})
    assert [x["id"] for x in manager_client.get(f"{API}/guests", params={"q": f"gold{u}"}).json()] == [g["id"]]
    assert manager_client.get(f"{API}/guests", params={"q": f"hidden{u}"}).json() == []


def test_unknown_or_bad_field_refused(manager_role_client, manager_client):
    u = _uniq()
    manager_role_client.post(f"{API}/fields", json={"target": "guest", "code": f"vip{u}", "title": "x",
                                                    "kind": "choice", "choices": ["Gold"]})
    r = manager_client.post(f"{API}/guests", json={"last_name": "Икс", "fields": {f"nope{u}": "1"}})
    assert r.status_code == 422 and r.json()["detail"] == f"Неизвестное поле: nope{u}"
    r = manager_client.post(f"{API}/guests", json={"last_name": "Икс", "fields": {f"vip{u}": "Silver"}})
    assert r.status_code == 422 and r.json()["detail"] == "Поле «x»: значения нет в списке"


def test_field_reindex_when_made_searchable(manager_role_client, manager_client):
    u = _uniq()
    f = manager_role_client.post(f"{API}/fields", json={"target": "guest", "code": f"yacht{u}", "title": "Яхта",
                                                        "kind": "text"}).json()
    g = _guest(manager_client, fields={f"yacht{u}": f"Пегас{u}"})
    assert manager_client.get(f"{API}/guests", params={"q": f"пегас{u}"}).json() == []
    manager_role_client.put(f"{API}/fields/{f['id']}", json={**f, "searchable": True})
    assert [x["id"] for x in manager_client.get(f"{API}/guests", params={"q": f"пегас{u}"}).json()] == [g["id"]]


def test_list_has_no_contact_fields(manager_client):
    _guest(manager_client, "Скрытов" + _uniq(), phone="+79160000001", birth_date="1980-01-02")
    rows = manager_client.get(f"{API}/guests", params={"q": "Скрытов"}).json()
    assert rows and not {"phone", "birth_date", "email", "preferences"} & set(rows[0])


def test_card_requires_guests_perm(manager_client, occupancy_client, mgmt_client):
    g = _guest(manager_client)
    assert occupancy_client.get(f"{API}/guests/{g['id']}").status_code == 403
    assert occupancy_client.get(f"{API}/guests", params={"q": "Орлов"}).status_code == 403
    assert mgmt_client.get(f"{API}/guests/{g['id']}").status_code == 200
    assert mgmt_client.put(f"{API}/guests/{g['id']}", json={"last_name": "Новый"}).status_code == 403


def test_preferences_and_special_dates_roundtrip(manager_client):
    g = _guest(manager_client, preferences={"allergy": "орехи", "food": "без глютена"},
               special_dates=[{"date": "2026-10-24", "what": "день рождения"}])
    card = manager_client.get(f"{API}/guests/{g['id']}").json()
    assert card["preferences"]["allergy"] == "орехи"
    assert card["special_dates"] == [{"date": "2026-10-24", "what": "день рождения"}]


def test_guest_update_audited_with_diff(manager_client, db):
    g = _guest(manager_client)
    r = manager_client.put(f"{API}/guests/{g['id']}", json={"last_name": "Орлов", "first_name": "Андрей",
                                                            "level": "vip"})
    assert r.status_code == 200 and r.json()["level"] == "vip"
    row = db.scalars(select(AuditLog).where(AuditLog.action == "stays_guest", AuditLog.target == f"guest:{g['id']}")
                     .order_by(AuditLog.id.desc())).first()
    assert json.loads(row.payload_json)["diff"]["level"] == ["regular", "vip"]


# ── B1: пол гостя, первичные семейные связи (addendum §3, §4) ─────────────────

def _link(c, a, b, kind, **kw):
    return c.post(f"{API}/guests/{a['id']}/links", json={"guest_id": b["id"], "kind": kind, **kw})


def test_gender_saved_and_validated(manager_client):
    g = _guest(manager_client, gender="f")
    assert g["gender"] == "f"
    assert manager_client.get(f"{API}/guests/{g['id']}").json()["gender"] == "f"
    assert manager_client.post(f"{API}/guests", json={"last_name": "Икс", "gender": "x"}).status_code == 422


def test_child_kind_replaced_by_parent(manager_client):
    a, b = _guest(manager_client), _guest(manager_client)
    r = _link(manager_client, a, b, "child")
    assert r.status_code == 422 and r.json()["detail"] == "Неизвестный вид связи"


def test_third_parent_422(manager_client):
    kid, p1, p2, p3 = (_guest(manager_client) for _ in range(4))
    assert _link(manager_client, p1, kid, "parent").status_code == 200
    assert _link(manager_client, p2, kid, "parent").status_code == 200
    r = _link(manager_client, p3, kid, "parent")
    assert r.status_code == 422 and r.json()["detail"] == "У ребёнка не больше двух родителей"


def test_cannot_be_own_ancestor(manager_client):
    grand, parent, kid = (_guest(manager_client) for _ in range(3))
    assert _link(manager_client, grand, parent, "parent").status_code == 200
    assert _link(manager_client, parent, kid, "parent").status_code == 200
    r = _link(manager_client, kid, grand, "parent")
    assert r.status_code == 422 and r.json()["detail"] == "Нельзя стать своим предком: этот гость — потомок ребёнка"


def test_spouse_cannot_be_descendant(manager_client):
    """Review Focus 2: супругом своего внука — 422, а не бесконечный обход."""
    grand, parent, kid = (_guest(manager_client) for _ in range(3))
    assert _link(manager_client, grand, parent, "parent").status_code == 200
    assert _link(manager_client, parent, kid, "parent").status_code == 200
    for a, b in ((grand, kid), (kid, grand)):
        r = _link(manager_client, a, b, "spouse")
        assert r.status_code == 422 and r.json()["detail"] == "Супругом нельзя сделать своего предка или потомка"


def test_spouse_link_is_undirected(manager_client):
    a, b = _guest(manager_client), _guest(manager_client)
    assert _link(manager_client, a, b, "spouse").status_code == 200
    r = _link(manager_client, b, a, "spouse")
    assert r.status_code == 409 and r.json()["detail"] == "Такая связь уже есть"


def test_former_only_for_spouse(manager_client):
    a, b = _guest(manager_client), _guest(manager_client)
    r = _link(manager_client, a, b, "parent", former=True)
    assert r.status_code == 422 and r.json()["detail"] == "«Бывшие» — только для супругов"


def test_former_spouse_gives_no_in_laws(manager_client):
    u = _uniq()
    me = _guest(manager_client, "Бывшев" + u, gender="m")
    ex = _guest(manager_client, "Бывшева" + u, gender="f")
    ex_mother = _guest(manager_client, "Мамина" + u, gender="f")
    assert _link(manager_client, me, ex, "spouse", former=True).status_code == 200
    assert _link(manager_client, ex_mother, ex, "parent").status_code == 200
    fam = manager_client.get(f"{API}/guests/{me['id']}/family").json()
    assert {k["person_id"]: k["title"] for k in fam["kin"]} == {ex["id"]: "бывшая жена"}
    labels = [x["label"] for x in manager_client.get(f"{API}/guests/{me['id']}").json()["links"]]
    assert labels == ["бывшая жена"]


def _owner_family(c):
    """Иван и Мария — супруги; у Ивана мать и её мать (бабушка), у Марии отец и мать."""
    u = _uniq()
    g = {k: _guest(c, last + u, first_name=first, gender=gender) for k, last, first, gender in (
        ("ivan", "Петров", "Иван", "m"), ("maria", "Петрова", "Мария", "f"),
        ("mother", "Петрова", "Ольга", "f"), ("grandma", "Смирнова", "Анна", "f"),
        ("m_father", "Козлов", "Виктор", "m"), ("m_mother", "Козлова", "Галина", "f"))}
    for a, b, kind in (("ivan", "maria", "spouse"), ("mother", "ivan", "parent"), ("grandma", "mother", "parent"),
                       ("m_father", "maria", "parent"), ("m_mother", "maria", "parent")):
        assert _link(c, g[a], g[b], kind).status_code == 200
    return g


def test_owner_example_via_api(manager_client, db):
    from sqlalchemy import func

    from app.modules.stays.adapters.orm import GuestLink

    g = _owner_family(manager_client)
    petr = _guest(manager_client, "Петров" + _uniq(), first_name="Пётр", gender="m")
    before = db.scalar(select(func.count(GuestLink.id)))
    assert _link(manager_client, g["ivan"], petr, "parent").status_code == 200
    assert _link(manager_client, g["maria"], petr, "parent").status_code == 200
    db.expire_all()
    assert db.scalar(select(func.count(GuestLink.id))) == before + 2       # только две связи «родитель»

    def kin(who):
        fam = manager_client.get(f"{API}/guests/{g[who]['id']}/family").json()
        return {k["person_id"]: k["title"] for k in fam["kin"]}

    assert kin("grandma")[petr["id"]] == "правнук"
    assert kin("m_father")[petr["id"]] == "внук" and kin("m_mother")[petr["id"]] == "внук"
    assert kin("maria")[g["mother"]["id"]] == "свекровь" and kin("ivan")[g["m_mother"]["id"]] == "тёща"


def test_family_endpoint_shape(manager_client):
    g = _owner_family(manager_client)
    fam = manager_client.get(f"{API}/guests/{g['ivan']['id']}/family").json()
    ids = {p["id"] for p in fam["people"]}
    assert ids == {x["id"] for x in g.values()}
    assert [g["mother"]["id"], g["grandma"]["id"]] in fam["parents"]
    assert [g["ivan"]["id"], g["maria"]["id"], False] in fam["spouses"]
    assert {k["title"] for k in fam["kin"]} == {"жена", "мать", "бабушка", "тесть", "тёща"}


def test_family_endpoint_visibility(manager_client, names_client, occupancy_client):
    g = _owner_family(manager_client)
    manager_client.put(f"{API}/guests/{g['maria']['id']}", json={
        "last_name": g["maria"]["last_name"], "first_name": "Мария", "gender": "f", "phone": "+79160000077",
        "birth_date": "1990-05-01"})
    url = f"{API}/guests/{g['ivan']['id']}/family"
    assert occupancy_client.get(url).status_code == 403
    names = names_client.get(url)
    assert names.status_code == 200
    people = names.json()["people"]
    assert people and all(set(p) == {"id", "name", "gender", "level"} for p in people)
    full = {p["id"]: p for p in manager_client.get(url).json()["people"]}
    assert full[g["maria"]["id"]]["phone"] == "+7 916 000-00-77"
    assert full[g["maria"]["id"]]["birth_date"] == "1990-05-01"
    assert manager_client.get(f"{API}/guests/999999999/family").status_code == 404


def test_relatives_among_occupants_on_card_and_day_board(manager_role_client, manager_client, names_client,
                                                         occupancy_client):
    """§4 «Где ещё»: у гостя — родственники среди проживающих, уровень «с фамилиями»."""
    from .helpers import create_res, make_category

    g = _owner_family(manager_client)
    cat = make_category(manager_role_client, n_units=2)
    res = create_res(manager_client, cat, "2031-03-10", "2031-03-14",
                     [(g["ivan"]["id"], "main", None, None), (g["maria"]["id"], "guest", None, None)])
    create_res(manager_client, cat, "2031-03-11", "2031-03-13", [(g["mother"]["id"], "main", None, None)])
    card = names_client.get(f"{API}/reservations/{res['id']}/card").json()
    rel = {o["guest_id"]: {(x["guest_id"], x["title"]) for x in o["relatives"]} for o in card["occupants"]}
    assert rel[g["ivan"]["id"]] == {(g["maria"]["id"], "жена"), (g["mother"]["id"], "мать")}
    assert rel[g["maria"]["id"]] == {(g["ivan"]["id"], "муж"), (g["mother"]["id"], "свекровь")}
    day = names_client.get(f"{API}/day", params={"date": "2031-03-12"}).json()
    guests = {x["guest_id"]: x for row in day["in_house"] for x in row["guests"]}
    assert {(x["title"], x["name"]) for x in guests[g["mother"]["id"]]["relatives"]} == {
        ("сын", guests[g["ivan"]["id"]]["name"]), ("невестка", guests[g["maria"]["id"]]["name"])}
    occ = occupancy_client.get(f"{API}/day", params={"date": "2031-03-12"}).json()
    assert all("guests" not in row for row in occ["in_house"])


def test_link_writes_take_module_lock(manager_client, monkeypatch):
    """Проверки графа и вставка/удаление связи — под lock_module (две записи одновременно не
    пропустят третьего родителя или супруга-предка)."""
    from app.modules.stays.application import guests as gmod

    calls = []
    real = gmod.lock_module
    monkeypatch.setattr(gmod, "lock_module", lambda s: (calls.append("lock"), real(s)))
    a, b = _guest(manager_client), _guest(manager_client)
    r = _link(manager_client, a, b, "parent")
    assert r.status_code == 200 and calls == ["lock"]
    assert manager_client.delete(f"{API}/guest-links/{r.json()['id']}").status_code == 200
    assert calls == ["lock", "lock"]


def test_second_current_spouse_422(manager_client):
    a, b, c = (_guest(manager_client) for _ in range(3))
    assert _link(manager_client, a, b, "spouse").status_code == 200
    for x, y in ((a, c), (c, b)):
        r = _link(manager_client, x, y, "spouse")
        assert r.status_code == 422 and r.json()["detail"] == "У гостя уже есть супруг(а)"
    # бывшие супруги не мешают: прежний брак — former, новый — действующий
    d = _guest(manager_client)
    assert _link(manager_client, a, d, "spouse", former=True).status_code == 200
    e = _guest(manager_client)
    assert _link(manager_client, d, e, "spouse").status_code == 200


def test_family_links_carry_ids(manager_client):
    """Редактор дерева удаляет связь крестиком на линии — граф отдаёт id каждой связи."""
    g = _owner_family(manager_client)
    fam = manager_client.get(f"{API}/guests/{g['ivan']['id']}/family").json()
    by_pair = {(ln["kind"], ln["a"], ln["b"]): ln for ln in fam["links"]}
    sp = by_pair[("spouse", g["ivan"]["id"], g["maria"]["id"])]
    assert sp["former"] is False and isinstance(sp["id"], int)
    assert ("parent", g["mother"]["id"], g["ivan"]["id"]) in by_pair
    assert len(fam["links"]) == len(fam["parents"]) + len(fam["spouses"])


def test_toggle_spouse_former(manager_client, monkeypatch, db):
    """«Бывшие» на линии супругов: переключается под замком модуля; снять «бывшие», когда у
    кого-то из пары уже есть действующий супруг, — 422; у не-супружеской связи — 422."""
    from app.modules.stays.application import guests as gmod

    a, b, c = (_guest(manager_client) for _ in range(3))
    link = _link(manager_client, a, b, "spouse").json()["id"]
    calls = []
    real = gmod.lock_module
    monkeypatch.setattr(gmod, "lock_module", lambda s: (calls.append("lock"), real(s)))
    r = manager_client.patch(f"{API}/guest-links/{link}", json={"former": True})
    assert r.status_code == 200 and r.json()["former"] is True and calls == ["lock"]
    label = {x["guest_id"]: x["label"] for x in manager_client.get(f"{API}/guests/{a['id']}").json()["links"]}
    assert label[b["id"]].startswith("бывш")
    assert _link(manager_client, a, c, "spouse").status_code == 200       # новый брак — действующий
    r = manager_client.patch(f"{API}/guest-links/{link}", json={"former": False})
    assert r.status_code == 422 and r.json()["detail"] == "У гостя уже есть супруг(а)"
    # повторная установка того же значения — без ошибки
    assert manager_client.patch(f"{API}/guest-links/{link}", json={"former": True}).status_code == 200
    kid = _guest(manager_client)
    parent = _link(manager_client, a, kid, "parent").json()["id"]
    r = manager_client.patch(f"{API}/guest-links/{parent}", json={"former": True})
    assert r.status_code == 422 and r.json()["detail"] == "«Бывшие» — только для супругов"
    assert manager_client.patch(f"{API}/guest-links/999999999", json={"former": True}).status_code == 422
    rows = db.scalars(select(AuditLog).where(AuditLog.action == "stays_guest_link",
                                             AuditLog.target == f"guest:{a['id']}")).all()
    assert any("former" in json.loads(x.payload_json or "{}") for x in rows)


def test_toggle_former_requires_edit(names_client, manager_client):
    a, b = _guest(manager_client), _guest(manager_client)
    link = _link(manager_client, a, b, "spouse").json()["id"]
    assert names_client.patch(f"{API}/guest-links/{link}", json={"former": True}).status_code == 403


def _guest_count(db) -> int:
    from sqlalchemy import func

    from app.modules.stays.adapters.orm import Guest
    db.expire_all()
    return db.scalar(select(func.count(Guest.id)))


def _link_count(db) -> int:
    from sqlalchemy import func

    from app.modules.stays.adapters.orm import GuestLink
    db.expire_all()
    return db.scalar(select(func.count(GuestLink.id)))


def test_new_guest_as_parent_in_one_transaction(manager_client, db):
    """«+ родитель» с новым гостем: гость и связь — одной записью под замком модуля."""
    kid = _guest(manager_client)
    r = manager_client.post(f"{API}/guests/{kid['id']}/links", json={
        "new_guest": {"last_name": "Мамина" + _uniq(), "first_name": "Ольга", "gender": "f"},
        "kind": "parent", "other_is_parent": True})
    assert r.status_code == 200, r.text
    mom = r.json()["guest_id"]
    assert manager_client.get(f"{API}/guests/{mom}").json()["gender"] == "f"
    fam = manager_client.get(f"{API}/guests/{kid['id']}/family").json()
    assert [kid["id"], mom] in fam["parents"]


def test_new_guest_third_parent_creates_nothing(manager_client, db):
    kid, p1, p2 = (_guest(manager_client) for _ in range(3))
    for p in (p1, p2):
        assert _link(manager_client, p, kid, "parent").status_code == 200
    guests_before, links_before = _guest_count(db), _link_count(db)
    r = manager_client.post(f"{API}/guests/{kid['id']}/links", json={
        "new_guest": {"last_name": "Лишний" + _uniq(), "first_name": "", "gender": "m"},
        "kind": "parent", "other_is_parent": True})
    assert r.status_code == 422 and r.json()["detail"] == "У ребёнка не больше двух родителей"
    assert (_guest_count(db), _link_count(db)) == (guests_before, links_before)


def test_new_child_of_both_spouses(manager_client):
    """«+ ребёнок … и ребёнок супруги»: обе связи parent — в той же записи."""
    dad, mom = _guest(manager_client, gender="m"), _guest(manager_client, gender="f")
    r = manager_client.post(f"{API}/guests/{dad['id']}/links", json={
        "new_guest": {"last_name": "Сынов" + _uniq(), "first_name": "Сын", "gender": "m"},
        "kind": "parent", "also_parent_id": mom["id"]})
    assert r.status_code == 200, r.text
    son = r.json()["guest_id"]
    parents = manager_client.get(f"{API}/guests/{son}/family").json()["parents"]
    assert sorted(p for c, p in parents if c == son) == sorted([dad["id"], mom["id"]])


def test_also_parent_failure_creates_nothing(manager_client, db):
    """Вторая связь «и ребёнок супруги» отклонена → не остаётся ни первой связи, ни нового гостя."""
    dad, mom, other = (_guest(manager_client) for _ in range(3))
    kid = _guest(manager_client)
    assert _link(manager_client, other, kid, "parent").status_code == 200
    links_before = _link_count(db)
    # dad → kid проходит (второй родитель), mom → kid — третий: отказ и откат первой связи
    r = manager_client.post(f"{API}/guests/{dad['id']}/links", json={
        "guest_id": kid["id"], "kind": "parent", "also_parent_id": mom["id"]})
    assert r.status_code == 422 and r.json()["detail"] == "У ребёнка не больше двух родителей"
    assert _link_count(db) == links_before
    # новый гость, второй родитель не найден — 422 после создания гостя и первой связи: откат всего
    guests_before = _guest_count(db)
    r = manager_client.post(f"{API}/guests/{dad['id']}/links", json={
        "new_guest": {"last_name": "Внуков" + _uniq()}, "kind": "parent", "also_parent_id": 999999999})
    assert r.status_code == 422 and r.json()["detail"] == "Гость не найден"
    assert (_guest_count(db), _link_count(db)) == (guests_before, links_before)


def test_link_target_validation(manager_client):
    a, b = _guest(manager_client), _guest(manager_client)
    url = f"{API}/guests/{a['id']}/links"
    both = {"guest_id": b["id"], "new_guest": {"last_name": "Икс"}, "kind": "parent"}
    assert manager_client.post(url, json=both).status_code == 422
    assert manager_client.post(url, json={"kind": "parent"}).status_code == 422
    for extra in ({"also_parent_id": a["id"]}, {"other_is_parent": True, "also_parent_id": b["id"]}):
        r = manager_client.post(url, json={"guest_id": b["id"], "kind": "parent", **extra})
        assert r.status_code == 422, extra
    r = manager_client.post(url, json={"guest_id": b["id"], "kind": "spouse", "other_is_parent": True})
    assert r.status_code == 422
