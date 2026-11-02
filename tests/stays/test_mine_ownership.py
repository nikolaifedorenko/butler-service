"""Часть 4, задача 1: права батлера на профиль и бронь, «свои» гости и брони — за всё время
(спецификация 2026-10-27-stays-butler-mine-design §2–§4, §7)."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import delete, select

from app.core.time import local_date
from app.modules.stays.adapters.orm import CoverageGuest, CoverageLine, Reservation, StayGroup
from app.modules.stays.application import mine

from .helpers import API, create_res, make_category, make_guest
from .test_fund_schema import iso_engine  # noqa: F401 — фикстура миграционного теста
from .test_occupancy_and_mine import _body, _doc


def _line(employee_id: int, day: dt.date, reservation_id: int | None = None, group_id: int | None = None,
          guests: tuple[int, ...] = ()) -> int:
    """Строка покрытия напрямую в БД: API назначений не пишет в прошлое."""
    from app.core.db import SessionLocal

    with SessionLocal() as s:
        ln = CoverageLine(day=day, employee_id=employee_id, reservation_id=reservation_id, group_id=group_id)
        s.add(ln)
        s.flush()
        s.add_all(CoverageGuest(coverage_id=ln.id, guest_id=g) for g in guests)
        s.commit()
        return ln.id


def _set_res(rid: int, **cols) -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as s:
        r = s.get(Reservation, rid)
        for k, v in cols.items():
            setattr(r, k, v)
        s.commit()


def _owns(db, employee_id: int) -> tuple[set[int], set[int]]:
    db.expire_all()
    return mine.my_reservation_ids(db, employee_id), mine.my_guest_ids(db, employee_id)


@pytest.fixture()
def stay(manager_role_client, manager_client):
    """Фабрика брони на дни [ci; co) от сегодня; гости — новые профили (первый — главный)."""
    cat = make_category(manager_role_client, n_units=3)

    def make(ci: int, co: int, n_guests: int = 1, **kw) -> dict:
        first, last = local_date() + dt.timedelta(days=ci), local_date() + dt.timedelta(days=co)
        gs = [make_guest(manager_client) for _ in range(n_guests)]
        r = create_res(manager_client, cat, first.isoformat(), last.isoformat(),
                       [(g["id"], "main" if i == 0 else "guest", None, None) for i, g in enumerate(gs)], **kw)
        return {"id": r["id"], "guests": [g["id"] for g in gs], "first": first}
    return make


def test_coverage_line_year_ago_own(stay, butlers, butler_client, db):
    r = stay(-400, -397)
    _line(butlers["a"], r["first"] + dt.timedelta(days=1), r["id"])
    rids, gids = _owns(db, butlers["a"])
    assert r["id"] in rids and r["guests"][0] in gids
    assert butler_client.get(f"{API}/guests/{r['guests'][0]}").status_code == 200
    assert butler_client.get(f"{API}/reservations/{r['id']}").status_code == 200


def test_future_line_own(stay, butlers, butler_client, db):
    r = stay(300, 303)
    _line(butlers["a"], r["first"] + dt.timedelta(days=2), r["id"])
    assert mine.owns_reservation(db, butlers["a"], r["id"]) and mine.owns_guest(db, butlers["a"], r["guests"][0])
    assert butler_client.get(f"{API}/guests/{r['guests'][0]}").status_code == 200


def test_no_lines_403(stay, butlers, butler_client, db):
    r = stay(5, 7)
    _line(butlers["b"], r["first"], r["id"])
    rids, gids = _owns(db, butlers["a"])
    assert r["id"] not in rids and r["guests"][0] not in gids
    assert not mine.owns_reservation(db, butlers["a"], r["id"])
    assert butler_client.get(f"{API}/guests/{r['guests'][0]}").status_code == 403
    assert butler_client.get(f"{API}/reservations/{r['id']}").status_code == 403
    assert butler_client.put(f"{API}/reservations/{r['id']}", json={
        "check_in": "2030-01-01", "check_out": "2030-01-02", "category_id": 1, "version": 1}).status_code == 403


def test_substitute_year_ago_still_own(stay, butlers, db):
    """Подменный батлер вёл гостей один день год назад — они его и после окончания подмены."""
    r = stay(-380, -376)
    first = r["first"]
    for i, e in ((0, butlers["b"]), (1, butlers["a"]), (2, butlers["b"]), (3, butlers["b"])):
        _line(e, first + dt.timedelta(days=i), r["id"])
    for e in (butlers["a"], butlers["b"]):
        rids, gids = _owns(db, e)
        assert r["id"] in rids and r["guests"][0] in gids


def test_tentative_reservation_own(stay, butlers, db):
    r = stay(10, 12, status="tentative")
    _line(butlers["a"], r["first"], r["id"])
    assert db.get(Reservation, r["id"]).status == "tentative"
    rids, gids = _owns(db, butlers["a"])
    assert r["id"] in rids and r["guests"][0] in gids


def test_explicit_other_butler_wins(stay, butlers, db):
    """Явный список гостей другого батлера сильнее строки «вся бронь» — по ночам (§4.2): в день,
    когда второго гостя явно ведёт Кузнецова, он не «свой» Иванову; бронь — своя."""
    r = stay(20, 23, n_guests=2)
    main, second = r["guests"]
    d0, d1 = r["first"], r["first"] + dt.timedelta(days=1)
    _line(butlers["a"], d0, r["id"])
    _line(butlers["b"], d0, r["id"], guests=(second,))
    rids, gids = _owns(db, butlers["a"])
    assert r["id"] in rids and main in gids and second not in gids
    assert second in mine.my_guest_ids(db, butlers["b"]) and main not in mine.my_guest_ids(db, butlers["b"])
    # явная строка другого батлера через группу брони — тоже сильнее
    g = StayGroup(title="группа")
    db.add(g)
    db.commit()
    _set_res(r["id"], group_id=g.id)
    _line(butlers["a"], d1, r["id"])
    _line(butlers["b"], d1, group_id=g.id, guests=(second,))
    assert second not in _owns(db, butlers["a"])[1]
    # в другой день Иванов ведёт бронь целиком без чужого явного списка — второй гость «свой»
    _line(butlers["a"], r["first"] + dt.timedelta(days=2), r["id"])
    assert second in _owns(db, butlers["a"])[1]


def test_group_line_owns_member_guests(stay, butlers, db):
    """Строка «вся группа» на день — гости всех броней группы, у которых в этот день ночь."""
    r1, r2, r3 = stay(30, 33), stay(31, 33), stay(32, 34)
    g = StayGroup(title="группа")
    db.add(g)
    db.commit()
    for r in (r1, r2, r3):
        _set_res(r["id"], group_id=g.id)
    _line(butlers["a"], r1["first"] + dt.timedelta(days=1), group_id=g.id)    # день 31: r1 и r2, r3 ещё нет
    rids, gids = _owns(db, butlers["a"])
    assert {r1["id"], r2["id"]} <= rids and r3["id"] not in rids
    assert {r1["guests"][0], r2["guests"][0]} <= gids and r3["guests"][0] not in gids


def test_created_by_butler_own(manager_client, butlers, butler_client, db):
    from app.modules.stays.adapters.orm import Guest

    g = make_guest(manager_client)
    assert butler_client.get(f"{API}/guests/{g['id']}").status_code == 403
    db.get(Guest, g["id"]).created_by_employee_id = butlers["a"]
    db.commit()
    assert g["id"] in mine.my_guest_ids(db, butlers["a"]) and mine.owns_guest(db, butlers["a"], g["id"])
    assert g["id"] not in mine.my_guest_ids(db, butlers["b"])
    assert butler_client.get(f"{API}/guests/{g['id']}").status_code == 200


def test_grants_split_migration(iso_engine):  # noqa: F811
    """0019: каждый грант stays.edit_mine (allow и deny, роль/группа/пользователь) → два гранта с тем
    же адресатом и действием; откат собирает пару обратно; колонка автора профиля — туда и обратно."""
    from alembic import command
    from sqlalchemy import inspect, text

    from app.bootstrap.schema_version import config

    engine = iso_engine
    q = text("SELECT group_id, user_id, role, permission, effect FROM access_grants "
             "WHERE permission LIKE 'stays.%mine%' ORDER BY permission, effect, role")
    command.downgrade(config(), "0018")
    try:
        assert "created_by_employee_id" not in {c["name"] for c in inspect(engine).get_columns("stays_guests")}
        with engine.begin() as c:
            c.execute(text("INSERT INTO access_groups (id, name, description, created_at) "
                           "VALUES (9191, 'Мигр19', '', '2026-01-01')"))
            c.execute(text("INSERT INTO access_grants (group_id, user_id, role, permission, effect) VALUES "
                           "(NULL, NULL, 'employee', 'stays.edit_mine', 'deny'), "
                           "(9191, NULL, '', 'stays.edit_mine', 'allow'), "
                           "(NULL, NULL, 'employee', 'stays.mine', 'allow')"))
        command.upgrade(config(), "head")
        with engine.connect() as c:
            assert c.execute(q).all() == [
                (None, None, "employee", "stays.mine", "allow"),
                (9191, None, "", "stays.mine_guest_edit", "allow"),
                (None, None, "employee", "stays.mine_guest_edit", "deny"),
                (9191, None, "", "stays.mine_res_edit", "allow"),
                (None, None, "employee", "stays.mine_res_edit", "deny")]
        assert "created_by_employee_id" in {c["name"] for c in inspect(engine).get_columns("stays_guests")}
        command.downgrade(config(), "0018")
        with engine.connect() as c:
            assert c.execute(q).all() == [
                (9191, None, "", "stays.edit_mine", "allow"),
                (None, None, "employee", "stays.edit_mine", "deny"),
                (None, None, "employee", "stays.mine", "allow")]
        assert "created_by_employee_id" not in {c["name"] for c in inspect(engine).get_columns("stays_guests")}
    finally:
        command.upgrade(config(), "head")


def test_view_default_everyone(db, employee_client):
    from app.core.permissions import ALL_KEYS, role_permissions

    for role in ("employee", "supervisor", "manager"):
        perms = role_permissions(db, role)
        assert {"stays.view", "stays.mine", "stays.mine_guest_edit", "stays.mine_res_edit"} <= perms, role
    assert "stays.edit_mine" not in ALL_KEYS
    assert "stays" in {m["id"] for m in employee_client.get("/api/auth/me").json()["menu"]}


def test_checked_out_reservation_edit_allowed_fields(stay, butlers, butler_client):
    """Бронь выехавшего год назад: разрешённые поля батлер правит без срока, запертые — 403."""
    r = stay(-370, -367)
    _set_res(r["id"], status="checked_out")
    _line(butlers["a"], r["first"], r["id"])
    doc = _doc(butler_client, r["id"])
    resp = butler_client.put(f"{API}/reservations/{r['id']}", json=_body(doc, note="дописал после выезда",
                             logistics=[{"kind": "car", "date": None, "time": "", "description": "A123BC"}]))
    assert resp.status_code == 200, resp.text
    after = _doc(butler_client, r["id"])
    assert after["note"] == "дописал после выезда" and after["status"] == "checked_out"
    resp = butler_client.put(f"{API}/reservations/{r['id']}", json=_body(after, check_out=after["check_in"]))
    assert resp.status_code == 403


@pytest.fixture()
def ivanov_grant(db):
    """Индивидуальный грант пользователю ivanov на время теста."""
    from app.core.identity import AccessGrant, User

    uid = db.scalar(select(User.id).where(User.username == "ivanov"))
    added: list[int] = []

    def grant(perm: str, effect: str = "deny") -> None:
        row = AccessGrant(user_id=uid, permission=perm, effect=effect)
        db.add(row)
        db.commit()
        added.append(row.id)
    yield grant
    db.execute(delete(AccessGrant).where(AccessGrant.id.in_(added)))
    db.commit()


def _guest_body(card: dict, **ch) -> dict:
    return {**{k: card[k] for k in ("last_name", "first_name", "middle_name", "email", "special", "vip_code_id",
                                    "note", "fields", "special_dates", "birth_date", "phone", "preferences")}, **ch}


def test_profile_read_no_audit_edit_audited(stay, butlers, butler_client, db):
    from sqlalchemy import func

    from app.core.audit import AuditLog

    r = stay(40, 42)
    gid = r["guests"][0]
    _line(butlers["a"], r["first"], r["id"])

    def count() -> int:
        return db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.target == f"guest:{gid}"))
    before = count()
    card = butler_client.get(f"{API}/guests/{gid}").json()
    assert count() == before
    resp = butler_client.put(f"{API}/guests/{gid}", json=_guest_body(card, preferences={"pillow": "пух"}))
    assert resp.status_code == 200, resp.text
    assert count() == before + 1


def test_guest_edit_needs_mine_guest_edit(stay, butlers, butler_client, ivanov_grant):
    """Без stays.mine_guest_edit профиль своего гостя — только чтение; правка брони — отдельное право."""
    r = stay(50, 52)
    gid = r["guests"][0]
    _line(butlers["a"], r["first"], r["id"])
    ivanov_grant("stays.mine_guest_edit")
    card = butler_client.get(f"{API}/guests/{gid}")
    assert card.status_code == 200
    assert butler_client.put(f"{API}/guests/{gid}", json=_guest_body(card.json(), note="x")).status_code == 403
    doc = _doc(butler_client, r["id"])
    assert butler_client.put(f"{API}/reservations/{r['id']}", json=_body(doc, note="можно")).status_code == 200


def test_reservation_edit_needs_mine_res_edit(stay, butlers, butler_client, ivanov_grant):
    r = stay(60, 62)
    gid = r["guests"][0]
    _line(butlers["a"], r["first"], r["id"])
    ivanov_grant("stays.mine_res_edit")
    doc = _doc(butler_client, r["id"])            # читать свою бронь — stays.mine
    assert butler_client.put(f"{API}/reservations/{r['id']}", json=_body(doc, note="нет")).status_code == 403
    card = butler_client.get(f"{API}/guests/{gid}").json()
    assert butler_client.put(f"{API}/guests/{gid}", json=_guest_body(card, note="можно")).status_code == 200
