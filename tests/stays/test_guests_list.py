"""Вкладка «Гости» (addendum §3): список с поиском, фильтрами и сортировкой, видимость телефона,
история проживаний и объединение дублей (переносы, общая бронь, семейные связи, предпросмотр)."""
from __future__ import annotations

import datetime as dt
import json
import uuid

from sqlalchemy import select

from app.core.audit import AuditLog
from app.core.time import local_date

from .helpers import API, create_res, make_category, uniq

LIST = f"{API}/guests/list"
MERGE = f"{API}/guests/merge"


def _guest(c, last: str, **kw) -> dict:
    r = c.post(f"{API}/guests", json={"last_name": last, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _list(c, **params) -> dict:
    r = c.get(LIST, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _ids(c, **params) -> list[int]:
    return [row["id"] for row in _list(c, **params)["rows"]]


def _phone() -> tuple[str, str, str]:
    """Уникальный телефон (база общая на тесты): ввод, отображение, цифры E.164."""
    n = f"{uuid.uuid4().int % 10**7:07d}"
    return f"8 916 {n}", f"+7 916 {n[:3]}-{n[3:5]}-{n[5:]}", f"7916{n}"


def _birth_in(days: int, years: int = 30) -> str:
    d = local_date() + dt.timedelta(days=days)
    try:
        return d.replace(year=d.year - years).isoformat()
    except ValueError:                      # 29 февраля — в невисокосный год ровно не попасть
        return (d - dt.timedelta(days=1)).replace(year=d.year - years).isoformat()


def test_guests_list_search_filters_sort(manager_role_client, manager_client):
    u = uniq()
    cat = make_category(manager_role_client, n_units=3)
    typed, shown, _ = _phone()
    a = _guest(manager_client, f"Альфа{u}", first_name="Анна", level="vip", phone=typed,
               birth_date=_birth_in(5))
    b = _guest(manager_client, f"Бета{u}", first_name="Борис", birth_date=_birth_in(40))
    c = _guest(manager_client, f"Гамма{u}", first_name="Вера", level="vvip")
    r1 = create_res(manager_client, cat, "2041-03-01", "2041-03-04", [(a["id"], "main", None, None)])
    create_res(manager_client, cat, "2041-05-10", "2041-05-12", [(a["id"], "main", None, None)])
    create_res(manager_client, cat, "2041-04-01", "2041-04-03", [(b["id"], "main", None, None)])
    cancelled = create_res(manager_client, cat, "2041-06-01", "2041-06-03", [(c["id"], "main", None, None)])
    r = manager_client.post(f"{API}/reservations/{cancelled['id']}/status",
                            json={"status": "cancelled", "version": cancelled["version"]})
    assert r.status_code == 200, r.text

    body = _list(manager_client, q=u)
    assert body["total"] == 3
    rows = {row["id"]: row for row in body["rows"]}
    assert rows[a["id"]] == {"id": a["id"], "name": f"Альфа{u} Анна", "level": "vip", "gender": "",
                             "phone": shown, "last_stay": "2041-05-10", "stays": 2}
    assert (rows[c["id"]]["stays"], rows[c["id"]]["last_stay"]) == (0, None)      # отменённая — не проживание
    # поиск по фамилии, по телефону (8 → 7), по номеру брони
    assert _ids(manager_client, q=f"бета{u}") == [b["id"]]
    assert _ids(manager_client, q=typed) == [a["id"]]
    assert _ids(manager_client, q=r1["number"].lower()) == [a["id"]]
    # фильтры: уровень, «был в периоде», «день рождения в ближайшие 30 дней»
    assert _ids(manager_client, q=u, level="vvip") == [c["id"]]
    assert _ids(manager_client, q=u, stayed_from="2041-04-02", stayed_to="2041-04-30") == [b["id"]]
    assert _ids(manager_client, q=u, stayed_from="2041-03-04", stayed_to="2041-03-31") == []   # день выезда — не ночь
    assert _ids(manager_client, q=u, stayed_from="2041-05-11") == [a["id"]]
    assert _ids(manager_client, q=u, birthday_days=30) == [a["id"]]
    # сортировка по колонкам в обе стороны, вторичный ключ — имя
    assert _ids(manager_client, q=u) == [a["id"], b["id"], c["id"]]
    assert _ids(manager_client, q=u, sort="name", dir="desc") == [c["id"], b["id"], a["id"]]
    assert _ids(manager_client, q=u, sort="stays", dir="desc") == [a["id"], b["id"], c["id"]]
    assert _ids(manager_client, q=u, sort="last_stay") == [c["id"], b["id"], a["id"]]
    assert _ids(manager_client, q=u, sort="level", dir="desc") == [c["id"], a["id"], b["id"]]
    # страница: total — все, rows — срез; больше 200 за раз нельзя
    page = _list(manager_client, q=u, offset=1, limit=1)
    assert page["total"] == 3 and [x["id"] for x in page["rows"]] == [b["id"]]
    assert manager_client.get(LIST, params={"limit": 201}).status_code == 422
    assert manager_client.get(LIST, params={"stayed_from": "2041-05-01", "stayed_to": "2041-04-01"}).status_code == 422
    # история проживаний гостя
    stays = manager_client.get(f"{API}/guests/{a['id']}/stays")
    assert stays.status_code == 200 and [s["date_from"] for s in stays.json()] == ["2041-05-10", "2041-03-01"]


def test_guests_list_phone_only_full_level(manager_client, names_client, mgmt_client):
    """Справочник — только полный уровень (stays.guests): ему телефоны и фильтр по дню рождения,
    уровню «с фамилиями» — 403 на список и историю проживаний."""
    u = uniq()
    typed, shown, digits = _phone()
    g = _guest(manager_client, f"Телефонов{u}", phone=typed, birth_date=_birth_in(3))
    assert [row["phone"] for row in _list(mgmt_client, q=u)["rows"]] == [shown]
    assert _ids(mgmt_client, q=digits) == [g["id"]]
    assert _ids(mgmt_client, q=u, birthday_days=30) == [g["id"]]
    assert names_client.get(LIST, params={"q": u}).status_code == 403
    assert names_client.get(f"{API}/guests/{g['id']}/stays").status_code == 403
    assert mgmt_client.get(f"{API}/guests/{g['id']}/stays").status_code == 200


def test_guests_tab_occupancy_403(occupancy_client, mgmt_client, manager_client):
    assert occupancy_client.get(LIST).status_code == 403
    a, b = _guest(manager_client, "Занятость" + uniq()), _guest(manager_client, "Занятость" + uniq())
    assert occupancy_client.post(MERGE, json={"keep_id": a["id"], "drop_id": b["id"]}).status_code == 403
    assert mgmt_client.post(MERGE, json={"keep_id": a["id"], "drop_id": b["id"]}).status_code == 403   # без stays.edit


def test_merge_guests_moves_everything(manager_role_client, manager_client, db):
    from app.modules.employees.application.catalog import Employee
    from app.modules.stays.adapters.orm import CoverageGuest, CoverageLine, Guest, Occupant

    u = uniq()
    code = "m" + u.lower()
    assert manager_role_client.post(f"{API}/fields", json={"target": "guest", "code": code, "title": "Клуб",
                                                            "kind": "text", "searchable": True}).status_code == 200
    cat = make_category(manager_role_client, n_units=2)
    keep = _guest(manager_client, f"Оставить{u}", first_name="Иван", note="ключи у охраны",
                  preferences={"food": "без глютена"}, special_dates=[{"date": "2020-05-01", "what": "годовщина"}])
    typed, _, digits = _phone()
    drop = _guest(manager_client, f"Дубль{u}", first_name="Ваня", middle_name="Петрович", phone=typed,
                  gender="m", level="vip", note="любит тишину",
                  preferences={"food": "веган", "allergy": "орехи"}, fields={code: f"золото{u}"},
                  special_dates=[{"date": "2020-05-01", "what": "годовщина"}, {"date": "2020-09-09", "what": "др жены"}])
    friend = _guest(manager_client, f"Друг{u}")
    r = manager_client.post(f"{API}/guests/{drop['id']}/links", json={"guest_id": friend["id"], "kind": "colleague"})
    assert r.status_code == 200
    res = create_res(manager_client, cat, "2042-02-01", "2042-02-04", [(drop["id"], "main", None, None)])
    emp = db.scalar(select(Employee.id).limit(1))
    line = CoverageLine(day=dt.date(2042, 2, 1), employee_id=emp, reservation_id=res["id"])
    db.add(line)
    db.flush()
    db.add(CoverageGuest(coverage_id=line.id, guest_id=drop["id"]))
    db.commit()

    r = manager_client.post(MERGE, json={"keep_id": keep["id"], "drop_id": drop["id"]})
    assert r.status_code == 200, r.text
    moves = r.json()["moves"]
    assert moves["reservations"] == [{"id": res["id"], "number": res["number"], "shared": False}]
    assert moves["links"] == [{"guest_id": friend["id"], "name": f"Друг{u}", "kind": "colleague", "former": False,
                               "result": "moved"}]
    assert moves["preferences"] == ["allergy"] and moves["fields"] == [code] and moves["coverage"] == 1
    assert moves["special_dates"] == [{"date": "2020-09-09", "what": "др жены"}]
    assert set(moves["profile"]) == {"middle_name", "phone", "gender", "level", "note"}

    db.expire_all()
    assert db.get(Guest, drop["id"]) is None
    assert [o.guest_id for o in db.scalars(select(Occupant).where(Occupant.reservation_id == res["id"]))] == [keep["id"]]
    assert db.scalar(select(CoverageGuest.guest_id).where(CoverageGuest.coverage_id == line.id)) == keep["id"]
    card = manager_client.get(f"{API}/guests/{keep['id']}").json()
    assert (card["first_name"], card["middle_name"], card["phone"], card["gender"], card["level"]) == \
        ("Иван", "Петрович", "+" + digits, "m", "vip")
    assert card["preferences"] == {"food": "без глютена", "allergy": "орехи"}         # своё побеждает
    assert card["fields"] == {code: f"золото{u}"}
    assert len(card["special_dates"]) == 2 and card["note"] == "ключи у охраны\nлюбит тишину"
    assert [(x["guest_id"], x["label"]) for x in card["links"]] == [(friend["id"], "коллега")]
    # поиск переиндексирован: телефон и поле с поиском дубля находят оставленного
    assert _ids(manager_client, q=digits) == [keep["id"]]
    assert _ids(manager_client, q=f"золото{u}") == [keep["id"]]
    a = db.scalars(select(AuditLog).where(AuditLog.action == "stays_guest_merge",
                                          AuditLog.target == f"guest:{keep['id']}")).one()
    payload = json.loads(a.payload_json)
    assert payload["drop_id"] == drop["id"]
    # в журнал — только то, что не перешло (значения keep победили), без перенесённых ПД
    assert payload["not_carried"] == {"last_name": f"Дубль{u}", "first_name": "Ваня", "preferences": {"food": "веган"}}
    assert payload["moves"]["reservations"][0]["id"] == res["id"]


def test_merge_guests_in_same_reservation(manager_role_client, manager_client):
    """Review Focus 1: оба — проживающие одной брони; бронь остаётся с одним гостем, без дубля
    и без ошибки уникальности, главный — там, где главным был любой из двух."""
    u = uniq()
    cat = make_category(manager_role_client, n_units=2)
    keep, drop, other = (_guest(manager_client, f"{n}{u}") for n in ("Оставить", "Дубль", "Другой"))
    res = create_res(manager_client, cat, "2042-03-01", "2042-03-06", [
        (drop["id"], "main", "2042-03-01", "2042-03-03"), (other["id"], "main", "2042-03-03", "2042-03-06"),
        (keep["id"], "guest", None, None)])
    simple = create_res(manager_client, cat, "2042-04-01", "2042-04-03", [
        (keep["id"], "main", None, None), (drop["id"], "guest", None, None)])
    r = manager_client.post(MERGE, json={"keep_id": keep["id"], "drop_id": drop["id"]})
    assert r.status_code == 200, r.text
    assert [x["shared"] for x in r.json()["moves"]["reservations"]] == [True, True]
    card = manager_client.get(f"{API}/reservations/{res['id']}").json()
    occ = sorted((o["guest_id"], o["role"], o["date_from"], o["date_to"]) for o in card["occupants"])
    assert occ == sorted([(keep["id"], "main", "2042-03-01", "2042-03-03"), (keep["id"], "guest", "2042-03-03", "2042-03-06"),
                          (other["id"], "main", "2042-03-03", "2042-03-06")])
    two = manager_client.get(f"{API}/reservations/{simple['id']}").json()
    assert [(o["guest_id"], o["role"]) for o in two["occupants"]] == [(keep["id"], "main")]
    # бронь после объединения сохраняется как есть: состав валиден, версия новая
    body = {k: card[k] for k in ("number", "check_in", "check_out", "category_id", "version")}
    body["occupants"] = [{k: o[k] for k in ("id", "guest_id", "role", "date_from", "date_to")} for o in card["occupants"]]
    assert card["version"] == res["version"] + 1
    put = manager_client.put(f"{API}/reservations/{res['id']}", json=body)
    assert put.status_code == 200, put.text


def test_merge_preview_equals_save(manager_role_client, manager_client, db):
    from app.modules.stays.adapters.orm import Guest, Occupant

    u = uniq()
    cat = make_category(manager_role_client, n_units=2)
    keep = _guest(manager_client, f"Оставить{u}")
    drop = _guest(manager_client, f"Дубль{u}", preferences={"habits": "ранний подъём"},
                  special_dates=[{"date": "2021-01-02", "what": "свадьба"}])
    child = _guest(manager_client, f"Ребёнок{u}")
    assert manager_client.post(f"{API}/guests/{drop['id']}/links",
                               json={"guest_id": child["id"], "kind": "parent"}).status_code == 200
    res = create_res(manager_client, cat, "2042-05-01", "2042-05-03", [(drop["id"], "main", None, None)])
    body = {"keep_id": keep["id"], "drop_id": drop["id"]}
    before = db.scalar(select(AuditLog.id).order_by(AuditLog.id.desc()).limit(1))
    pv = manager_client.post(MERGE, params={"preview": 1}, json=body)
    assert pv.status_code == 200, pv.text
    assert pv.json()["preview"] is True
    db.expire_all()
    assert db.get(Guest, drop["id"]) is not None                                      # ничего не сохранено
    assert db.scalar(select(Occupant.guest_id).where(Occupant.reservation_id == res["id"])) == drop["id"]
    assert db.scalar(select(AuditLog.id).order_by(AuditLog.id.desc()).limit(1)) == before
    sv = manager_client.post(MERGE, json=body)
    assert sv.status_code == 200, sv.text
    assert sv.json()["preview"] is False
    assert pv.json()["moves"] == sv.json()["moves"]
    assert pv.json()["moves"]["links"][0]["result"] == "moved" and pv.json()["moves"]["preferences"] == ["habits"]


def test_merge_keeps_family_links_without_duplicates(manager_client, db):
    from app.modules.stays.adapters.orm import Guest, GuestLink

    u = uniq()
    keep, drop, child, wife, mom = (_guest(manager_client, f"{n}{u}", gender=g) for n, g in
                                    (("Оставить", "m"), ("Дубль", "m"), ("Сын", "m"), ("Жена", "f"), ("Мать", "f")))

    def link(a, b, kind, former=False):
        r = manager_client.post(f"{API}/guests/{a['id']}/links", json={"guest_id": b["id"], "kind": kind, "former": former})
        assert r.status_code == 200, r.text

    link(keep, child, "parent")
    link(drop, child, "parent")                 # тот же ребёнок у обоих — после объединения одна связь
    link(drop, wife, "spouse")
    link(mom, drop, "parent")
    link(keep, drop, "relative")                # связь между самими объединяемыми — удаляется
    r = manager_client.post(MERGE, json={"keep_id": keep["id"], "drop_id": drop["id"]})
    assert r.status_code == 200, r.text
    assert sorted((x["name"], x["result"]) for x in r.json()["moves"]["links"]) == sorted(
        [(f"Сын{u}", "duplicate"), (f"Жена{u}", "moved"), (f"Мать{u}", "moved"), (f"Оставить{u}", "removed")])
    rows = db.scalars(select(GuestLink).where((GuestLink.guest_a_id == keep["id"]) | (GuestLink.guest_b_id == keep["id"]))).all()
    assert sorted((x.guest_a_id, x.guest_b_id, x.kind) for x in rows) == sorted(
        [(keep["id"], child["id"], "parent"), (keep["id"], wife["id"], "spouse"), (mom["id"], keep["id"], "parent")])
    fam = manager_client.get(f"{API}/guests/{child['id']}/family").json()
    kin = {k["person_id"]: k["title"] for k in fam["kin"]}
    assert kin[keep["id"]] == "отец" and kin[mom["id"]] == "бабушка" and kin.get(wife["id"]) != "мать"
    assert drop["id"] not in kin

    # нарушение семейного дерева — 409 с объяснением и без изменений
    a, b, wa, wb, kid = (_guest(manager_client, f"{n}{u}") for n in ("А", "Б", "ЖенаА", "ЖенаБ", "Внук"))
    link(a, wa, "spouse")
    link(b, wb, "spouse")
    r = manager_client.post(MERGE, json={"keep_id": a["id"], "drop_id": b["id"]})
    assert r.status_code == 409 and r.json()["detail"] == "Объединение нарушит семейное дерево: У гостя уже есть супруг(а)"
    db.expire_all()
    assert db.get(Guest, b["id"]) is not None
    c, d = _guest(manager_client, f"В{u}"), _guest(manager_client, f"Г{u}")
    link(c, kid, "parent")
    link(kid, d, "parent")                      # Г — внук В: объединение сделало бы В своим предком
    r = manager_client.post(MERGE, json={"keep_id": c["id"], "drop_id": d["id"]})
    assert r.status_code == 409 and r.json()["detail"] == \
        "Объединение нарушит семейное дерево: Нельзя стать своим предком: этот гость — потомок ребёнка"
    assert db.get(Guest, d["id"]) is not None
    assert manager_client.post(MERGE, json={"keep_id": a["id"], "drop_id": a["id"]}).status_code == 422


def test_merge_spouse_current_beats_former(manager_client, db):
    """У keep с W бывший брак, у дубля с W — действующий: остаётся действующий брак keep–W,
    связь дубля удаляется; если у keep уже есть другой действующий супруг — 409."""
    from app.modules.stays.adapters.orm import Guest, GuestLink

    u = uniq()
    keep, drop, w = (_guest(manager_client, f"{n}{u}") for n in ("Оставить", "Дубль", "Жена"))

    def link(a, b, former):
        r = manager_client.post(f"{API}/guests/{a['id']}/links", json={"guest_id": b["id"], "kind": "spouse", "former": former})
        assert r.status_code == 200, r.text

    link(keep, w, True)
    link(w, drop, False)
    r = manager_client.post(MERGE, json={"keep_id": keep["id"], "drop_id": drop["id"]})
    assert r.status_code == 200, r.text
    assert [(x["guest_id"], x["result"]) for x in r.json()["moves"]["links"]] == [(w["id"], "current")]
    rows = db.scalars(select(GuestLink).where(GuestLink.kind == "spouse", (GuestLink.guest_a_id == w["id"])
                                              | (GuestLink.guest_b_id == w["id"]))).all()
    assert [(x.guest_a_id, x.guest_b_id, x.former) for x in rows] == [(keep["id"], w["id"], False)]

    k2, d2, w2, x2 = (_guest(manager_client, f"{n}2{u}") for n in ("Оставить", "Дубль", "Жена", "Другая"))
    link(k2, w2, True)
    link(k2, x2, False)
    link(d2, w2, False)
    r = manager_client.post(MERGE, json={"keep_id": k2["id"], "drop_id": d2["id"]})
    assert r.status_code == 409 and r.json()["detail"] == "Объединение нарушит семейное дерево: У гостя уже есть супруг(а)"
    db.expire_all()
    assert db.get(Guest, d2["id"]) is not None
