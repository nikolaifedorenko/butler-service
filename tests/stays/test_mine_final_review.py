"""Часть 4, финальное ревью ветки: поиск ниже полного уровня — только по ФИО и номеру брони
(решение 8), правка брони батлером не делает чужого проживающего своим (решение 9), автор профиля
при слиянии (решение 10), «Все мои гости» — прошлые и следующий заезд, семейные связи — только
семьи проживающих, явный список — только по живой брони, история своей брони целиком, «Сегодня» —
бронь без состава (спецификация 2026-10-27-stays-butler-mine-design §3)."""
from __future__ import annotations

import datetime as dt

from app.modules.stays.adapters.orm import Guest
from app.modules.stays.application import family, mine

from .helpers import API, create_res, make_category, make_guest, uniq
from .test_mine_edit import _link
from .test_mine_ownership import _line, _set_res
from .test_mine_screens import D, on_day  # noqa: F401 — фикстура
from .test_occupancy_and_mine import _body, _doc

PHONE = "+79165550188"


def _vip(manager_client, u: str) -> dict:
    """Чужой гость с телефоном и почтой; фамилия — без цифр, чтобы цифры совпадали только с телефоном."""
    r = manager_client.post(f"{API}/guests", json={"last_name": f"Тайнов{u}", "first_name": "Пётр",
                                                    "phone": PHONE, "email": f"secret.vip.{u.lower()}@example.com"})
    assert r.status_code == 200, r.text
    return r.json()


def _ids(resp) -> set[int]:
    assert resp.status_code == 200, resp.text
    return {g["id"] for g in resp.json()}


# ── решение 8: поиск ниже полного уровня — только ФИО и номер брони ─────────────────────────

def _pd_setup(manager_role_client, manager_client, butlers) -> dict:
    u = uniq()
    g = _vip(manager_client, u)
    d = butlers["days"][0]
    cat = make_category(manager_role_client, n_units=2)
    r = create_res(manager_client, cat, d.isoformat(), (d + dt.timedelta(days=2)).isoformat(),
                   [(g["id"], "main", None, None)], number=f"N{u}", customer=f"Заказчиксекрет{u}")
    return {"u": u, "g": g, "r": r, "d": d}


def _pd_queries(s: dict) -> dict[str, str]:
    return {"phone": "5550188", "prefix": "7916555", "email": f"secret.vip.{s['u'].lower()}",
            "customer": f"заказчиксекрет{s['u'].lower()}"}


def test_guest_search_names_level_only_names(manager_role_client, manager_client, butlers, butler_client,
                                             names_client):
    s = _pd_setup(manager_role_client, manager_client, butlers)
    gid = s["g"]["id"]
    for c in (butler_client, names_client):
        for what, q in _pd_queries(s).items():
            assert gid not in _ids(c.get(f"{API}/guests", params={"q": q})), what
        assert gid in _ids(c.get(f"{API}/guests", params={"q": f"тайнов{s['u']}"}))
    # полный уровень ищет как раньше: по телефону, его началу и почте
    for q in ("5550188", "7916555", "89165550188", f"secret.vip.{s['u'].lower()}"):
        assert gid in _ids(manager_client.get(f"{API}/guests", params={"q": q})), q


def test_guest_search_mine_names_level_only_names(manager_role_client, manager_client, butlers, butler_client):
    """mine=1: даже свой гость ниже полного уровня ищется только по ФИО."""
    s = _pd_setup(manager_role_client, manager_client, butlers)
    _line(butlers["a"], s["d"], s["r"]["id"])
    gid = s["g"]["id"]
    assert gid in _ids(butler_client.get(f"{API}/guests", params={"q": f"Тайнов{s['u']}", "mine": 1}))
    for q in ("5550188", "7916555", f"secret.vip.{s['u'].lower()}"):
        assert gid not in _ids(butler_client.get(f"{API}/guests", params={"q": q, "mine": 1})), q


def _board_ids(c, s: dict, q: str) -> set[int]:
    resp = c.get(f"{API}/board/units", params={"first": s["d"].isoformat(), "last": s["d"].isoformat(), "q": q})
    assert resp.status_code == 200, resp.text
    return {b["reservation_id"] for b in resp.json()["bars"]}


def _day_ids(c, s: dict, q: str) -> set[int]:
    resp = c.get(f"{API}/day", params={"date": s["d"].isoformat(), "q": q})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return {x["reservation_id"] for k in ("arrivals", "in_house", "departures") for x in body[k]}


def _bookings_ids(c, s: dict, q: str) -> set[int]:
    resp = c.get(f"{API}/bookings", params={"first": s["d"].isoformat(),
                                            "last": (s["d"] + dt.timedelta(days=1)).isoformat(), "q": q})
    assert resp.status_code == 200, resp.text
    return {x["id"] for x in resp.json()["rows"]}


def test_boards_and_bookings_search_names_level(manager_role_client, manager_client, butlers, butler_client,
                                               names_client):
    """Шахматка объектов, табло дня и «Брони»: телефон, его начало, почта и заказчик ниже полного
    уровня бронь не находят; фамилия и номер — находят; полный уровень — как раньше."""
    s = _pd_setup(manager_role_client, manager_client, butlers)
    rid = s["r"]["id"]
    for find in (_board_ids, _day_ids, _bookings_ids):
        for c in (butler_client, names_client):
            for what, q in _pd_queries(s).items():
                assert rid not in find(c, s, q), (find.__name__, what)
            assert rid in find(c, s, f"Тайнов{s['u']}"), find.__name__
            assert rid in find(c, s, f"n{s['u'].lower()}"), find.__name__
        for what, q in _pd_queries(s).items():
            assert rid in find(manager_client, s, q), (find.__name__, what)


# ── решение 9: правка брони батлером не делает чужого проживающего своим ────────────────────

def _foreign_occupant(manager_role_client, manager_client, butlers) -> dict:
    """Бронь [d; d+3): главный M все ночи, F — только ночи d+1 и d+2. Иванов ведёт бронь в ночь d
    (строкой «вся бронь»), Кузнецова — в d+1 и d+2: F — не свой Иванову."""
    d = butlers["days"][0]
    cat = make_category(manager_role_client, n_units=2)
    m, f = make_guest(manager_client), make_guest(manager_client)
    iso = lambda k: (d + dt.timedelta(days=k)).isoformat()  # noqa: E731
    r = create_res(manager_client, cat, iso(0), iso(3), [(m["id"], "main", None, None), (f["id"], "guest", iso(1), None)])
    _line(butlers["a"], d, r["id"])
    for k in (1, 2):
        _line(butlers["b"], d + dt.timedelta(days=k), r["id"])
    return {"r": r, "m": m["id"], "f": f["id"], "d": d}


def test_butler_cannot_extend_foreign_occupant_onto_own_night(manager_role_client, manager_client, butlers,
                                                              butler_client, db):
    s = _foreign_occupant(manager_role_client, manager_client, butlers)
    rid, f = s["r"]["id"], s["f"]
    assert not mine.owns_guest(db, butlers["a"], f)
    doc = _doc(butler_client, rid)
    occ = [{**o, "date_from": s["d"].isoformat()} if o["guest_id"] == f else o for o in doc["occupants"]]
    for preview in (True, False):
        resp = butler_client.put(f"{API}/reservations/{rid}", params={"preview": preview},
                                 json=_body(doc, occupants=occ))
        assert resp.status_code == 403, (preview, resp.text)
    # вторая запись того же гостя на свою ночь — тоже
    occ2 = doc["occupants"] + [{"guest_id": f, "role": "guest", "date_from": s["d"].isoformat(),
                                "date_to": (s["d"] + dt.timedelta(days=1)).isoformat()}]
    for preview in (True, False):
        resp = butler_client.put(f"{API}/reservations/{rid}", params={"preview": preview},
                                 json=_body(doc, occupants=occ2))
        assert resp.status_code == 403, (preview, resp.text)
    db.expire_all()
    assert not mine.owns_guest(db, butlers["a"], f)
    assert butler_client.get(f"{API}/guests/{f}").status_code == 403
    after = _doc(manager_client, rid)
    assert [(o["guest_id"], o["date_from"]) for o in after["occupants"]] == \
        [(o["guest_id"], o["date_from"]) for o in doc["occupants"]]
    # правка, не открывающая чужого, проходит
    resp = butler_client.put(f"{API}/reservations/{rid}", json=_body(doc, note="ключи на ресепшене"))
    assert resp.status_code == 200, resp.text


def test_butler_new_relative_may_become_own(manager_role_client, manager_client, butlers, butler_client, db):
    """Новый проживающий — родственник — своим стать может (правило состава, решение 9)."""
    s = _foreign_occupant(manager_role_client, manager_client, butlers)
    rid = s["r"]["id"]
    son = make_guest(manager_client)["id"]
    assert _link(manager_client, s["m"], son, "parent").status_code == 200
    doc = _doc(butler_client, rid)
    occ = doc["occupants"] + [{"guest_id": son, "role": "guest", "date_from": doc["check_in"],
                               "date_to": doc["check_out"]}]
    resp = butler_client.put(f"{API}/reservations/{rid}", json=_body(doc, occupants=occ))
    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert mine.owns_guest(db, butlers["a"], son)


# ── п. 3: «Все мои гости» — прошлые проживания и следующий заезд ─────────────────────────────

def test_all_guests_last_and_next_stay(manager_role_client, manager_client, butlers, butler_client, on_day):
    u = uniq()
    cat = make_category(manager_role_client, n_units=2)
    g = make_guest(manager_client, f"Заездов{u}")
    past = create_res(manager_client, cat, "2044-05-01", "2044-05-03", [(g["id"], "main", None, None)])
    now = create_res(manager_client, cat, "2044-06-09", "2044-06-12", [(g["id"], "main", None, None)])
    near = create_res(manager_client, cat, "2044-07-01", "2044-07-03", [(g["id"], "main", None, None)])
    far = create_res(manager_client, cat, "2044-08-01", "2044-08-03", [(g["id"], "main", None, None)])
    for r in (past, now, near, far):
        _line(butlers["a"], D(r["check_in"]), r["id"])
    on_day(D("2044-06-10"))
    (row,) = butler_client.get(f"{API}/mine/guests", params={"q": f"заездов{u}"}).json()["rows"]
    assert (row["stays"], row["last_stay"], row["next_stay"]) == (2, "2044-06-09", "2044-07-01")


# ── решение 10: слияние и автор профиля ──────────────────────────────────────────────────────

def _merge(manager_client, keep: int, drop: int):
    resp = manager_client.post(f"{API}/guests/merge", json={"keep_id": keep, "drop_id": drop})
    assert resp.status_code == 200, resp.text


def test_merge_clears_author_unless_same(manager_client, butlers, db):
    from .helpers import set_guest

    a, b = butlers["a"], butlers["b"]
    ids = [make_guest(manager_client)["id"] for _ in range(6)]
    for gid, author in zip(ids, (a, None, None, a, a, a), strict=True):
        set_guest(gid, created_by_employee_id=author)
    set_guest(ids[5], created_by_employee_id=b)
    _merge(manager_client, ids[0], ids[1])            # автор только у оставляемого — снят
    _merge(manager_client, ids[2], ids[3])            # автор только у дубля — не переходит
    _merge(manager_client, ids[4], ids[5])            # разные авторы — снят
    db.expire_all()
    assert [db.get(Guest, i).created_by_employee_id for i in (ids[0], ids[2], ids[4])] == [None, None, None]
    same = [make_guest(manager_client)["id"] for _ in range(2)]
    for gid in same:
        set_guest(gid, created_by_employee_id=a)
    _merge(manager_client, *same)
    db.expire_all()
    assert db.get(Guest, same[0]).created_by_employee_id == a


# ── п. 5: родня проживающих — только связи их семей ──────────────────────────────────────────

def test_relatives_among_reads_only_their_families(manager_client, monkeypatch, db):
    """Читаются только связи семей проживающих и кандидатов (связный граф): связей чужих семей
    нет ни в одном запросе, каждый запрос к связям — с фильтром по людям; ответ — тот же."""
    from sqlalchemy import event

    from app.core.db import engine

    husband, wife, granny, stranger = (make_guest(manager_client)["id"] for _ in range(4))
    assert _link(manager_client, husband, wife, "spouse").status_code == 200
    assert _link(manager_client, granny, wife, "parent").status_code == 200
    p, ch = (make_guest(manager_client)["id"] for _ in range(2))           # чужая семья
    assert _link(manager_client, p, ch, "parent").status_code == 200
    loaded: list[set[int]] = []
    real = family.family_links

    def spy(db_, seeds):
        links = real(db_, seeds)
        loaded.append({x for ln in links for x in (ln.guest_a_id, ln.guest_b_id)})
        return links
    monkeypatch.setattr(family, "family_links", spy)
    stmts: list[str] = []

    def before(conn, cur, stmt, params, ctx, many):
        stmts.append(" ".join(stmt.split()).upper())
    event.listen(engine, "before_cursor_execute", before)
    try:
        got = family.relatives_among(db, {husband}, {granny, stranger})
    finally:
        event.remove(engine, "before_cursor_execute", before)
    assert got == {granny}
    assert loaded == [{husband, wife, granny}]
    links_q = [s for s in stmts if "FROM STAYS_GUEST_LINKS" in s]
    assert links_q and all(" IN " in s.split("WHERE", 1)[-1] for s in links_q if "WHERE" in s)
    assert all("WHERE" in s for s in links_q)


# ── п. 6: явный список гостей — только по живой брони ────────────────────────────────────────

def test_explicit_line_on_cancelled_reservation_not_own(manager_role_client, manager_client, butlers, db):
    d = butlers["days"][0]
    cat = make_category(manager_role_client, n_units=1)
    g = make_guest(manager_client)
    r = create_res(manager_client, cat, d.isoformat(), (d + dt.timedelta(days=2)).isoformat(),
                   [(g["id"], "main", None, None)])
    _line(butlers["a"], d, r["id"], guests=(g["id"],))
    db.expire_all()
    assert mine.owns_guest(db, butlers["a"], g["id"])
    _set_res(r["id"], status="cancelled")
    db.expire_all()
    assert not mine.owns_guest(db, butlers["a"], g["id"])


# ── п. 7: история своей брони — целиком ──────────────────────────────────────────────────────

def test_own_reservation_history_full(own_reservation, butler_client, manager_client):
    rid = own_reservation["mine"]["id"]
    doc = _doc(manager_client, rid)
    assert manager_client.put(f"{API}/reservations/{rid}", json=_body(doc, customer="Фирма-заказчик")).status_code == 200
    hist = butler_client.get(f"{API}/reservations/{rid}/history").json()
    assert any("customer" in h["diff"] for h in hist)
    other = own_reservation["other"]["id"]
    doc = _doc(manager_client, other)
    assert manager_client.put(f"{API}/reservations/{other}", json=_body(doc, customer="Другая фирма")).status_code == 200
    assert not any("customer" in h["diff"] for h in butler_client.get(f"{API}/reservations/{other}/history").json())


# ── п. 8: «Сегодня» — пустой состав только у брони без проживающих ───────────────────────────

def test_today_departing_without_led_guest_not_shown(manager_role_client, manager_client, butlers, butler_client,
                                                     on_day):
    """Явный список Иванова прошлой ночью — гость, уже выехавший раньше; остальных вела Кузнецова:
    бронь, выезжающая сегодня, не попадает в «Сегодня» пустой карточкой. Бронь без состава — попадает."""
    cat = make_category(manager_role_client, n_units=3)
    m, early = make_guest(manager_client), make_guest(manager_client)
    r = create_res(manager_client, cat, "2044-09-07", "2044-09-10",
                   [(m["id"], "main", None, None), (early["id"], "guest", None, "2044-09-08")])
    _line(butlers["a"], D("2044-09-09"), r["id"], guests=(early["id"],))
    _line(butlers["b"], D("2044-09-09"), r["id"], guests=(m["id"],))
    empty = create_res(manager_client, cat, "2044-09-08", "2044-09-10")
    _line(butlers["a"], D("2044-09-09"), empty["id"])
    on_day(D("2044-09-10"))
    rows = {x["reservation_id"]: x for x in butler_client.get(f"{API}/mine/today").json()["reservations"]}
    assert r["id"] not in rows
    assert rows[empty["id"]]["guests"] == [] and rows[empty["id"]]["departing"] is True
