"""Публикация фонда (спецификация stays-fund-versions §4.3, §4.4): перенос правок в поздние версии
поле за полем относительно базы черновика, массовый перевод броней на категорию, предпросмотр
публикации тем же кодом с откатом."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import delete, func, select, text

from app.core.audit import AuditLog
from app.modules.stays.adapters.orm import (
    Category,
    CategoryState,
    FundGroup,
    FundVersion,
    GroupState,
    Move,
    Reservation,
    Unit,
    UnitFlag,
    UnitLineage,
    UnitState,
    UnitStateFlag,
)
from app.modules.stays.application import fund_drafts as fd
from app.modules.stays.application.fund import FundConflict
from app.modules.stays.application.fund_versions import fund_on

from .helpers import API, create_res, make_category

# ── перенос в поздние версии (без API) ──────────────────────────────────────

V0 = dt.date(2096, 1, 1)
NOW = "2096-01-10"
D = dt.date(2096, 2, 1)           # черновик
L = dt.date(2096, 3, 1)           # поздняя версия
LO, HI = dt.date(2096, 1, 1), dt.date(2097, 1, 1)


@pytest.fixture()
def world(db, today):
    """Основа V0: категории A и B, узел Корпус, объекты 4003 (A, флаг) и 4004 (B)."""
    today(NOW)
    max_unit = db.scalar(select(func.coalesce(func.max(Unit.id), 0)))
    max_cat = db.scalar(select(func.coalesce(func.max(Category.id), 0)))
    max_grp = db.scalar(select(func.coalesce(func.max(FundGroup.id), 0)))
    flag = UnitFlag(title=f"тест-флаг-перенос-{max_unit}")
    a, b, g, u1, u2 = Category(), Category(), FundGroup(), Unit(), Unit()
    db.add_all([flag, a, b, g, u1, u2])
    db.flush()
    v = FundVersion(valid_from=V0, status="published", rev=1)
    db.add(v)
    db.flush()
    db.add_all([CategoryState(version_id=v.id, category_id=a.id, code="PA", title="Кат А"),
                CategoryState(version_id=v.id, category_id=b.id, code="PB", title="Кат Б"),
                GroupState(version_id=v.id, group_id=g.id, parent_id=None, title="Корпус")])
    db.flush()
    db.add_all([UnitState(version_id=v.id, unit_id=u1.id, label="4003", category_id=a.id, group_id=g.id, floor="4"),
                UnitState(version_id=v.id, unit_id=u2.id, label="4004", category_id=b.id, group_id=g.id, floor="4")])
    db.flush()
    db.add(UnitStateFlag(version_id=v.id, unit_id=u1.id, flag_id=flag.id))
    db.commit()
    yield {"v0": v.id, "a": a.id, "b": b.id, "g": g.id, "u1": u1.id, "u2": u2.id, "flag": flag.id}
    db.rollback()
    ids = list(db.scalars(select(FundVersion.id).where(FundVersion.valid_from >= LO, FundVersion.valid_from < HI)))
    from sqlalchemy import update
    db.execute(update(FundVersion).where(FundVersion.base_version_id.in_(ids)).values(base_version_id=None))
    db.execute(delete(UnitLineage).where(UnitLineage.version_id.in_(ids)))
    for model in (UnitStateFlag, UnitState, GroupState, CategoryState):
        db.execute(delete(model).where(model.version_id.in_(ids)))
    db.execute(delete(FundVersion).where(FundVersion.id.in_(ids)))
    db.execute(delete(UnitFlag).where(UnitFlag.title.like("тест-флаг-перенос-%")))
    db.execute(delete(Unit).where(Unit.id > max_unit))
    db.execute(delete(Category).where(Category.id > max_cat))
    db.execute(delete(FundGroup).where(FundGroup.id > max_grp))
    db.execute(delete(AuditLog).where(AuditLog.action == "stays_fund_version", AuditLog.actor_name == "system"))
    db.commit()


def _later(db, edit) -> int:
    """Опубликовать позднюю версию с L: edit(rev) правит её черновик."""
    d = fd.open_draft(db, L, None)
    edit(d.rev)
    return fd.publish(db, None).version.id


def _unit(db, day, uid):
    return fund_on(db, day).units.get(uid)


def test_propagate_untouched_field(db, world):
    _later(db, lambda rev: fd.save_unit(db, rev, {"floor": "5"}, world["u2"]))
    d = fd.open_draft(db, D, None)
    fd.save_unit(db, d.rev, {"floor": "7"}, world["u1"])
    res = fd.publish(db, None)
    assert _unit(db, L, world["u1"]).floor == "7"               # поздняя версия поле не меняла
    assert _unit(db, L, world["u2"]).floor == "5"               # её собственная правка на месте
    assert [(p["entity"], p["id"], p["field"], p["valid_from"]) for p in res.propagated] == [
        ("unit", world["u1"], "floor", L.isoformat())]
    assert res.kept == [] and res.skipped == []


def test_propagate_keeps_later_own_change(db, world):
    _later(db, lambda rev: fd.save_unit(db, rev, {"floor": "9", "label": "4103"}, world["u1"]))
    d = fd.open_draft(db, D, None)
    fd.save_unit(db, d.rev, {"floor": "7", "category_id": world["b"]}, world["u1"])
    res = fd.publish(db, None)
    later = _unit(db, L, world["u1"])
    assert (later.floor, later.label, later.category_id) == ("9", "4103", world["b"])
    assert _unit(db, D, world["u1"]).floor == "7"
    assert [(k["id"], k["field"], k["value"]) for k in res.kept] == [(world["u1"], "floor", "9")]
    assert [(p["id"], p["field"]) for p in res.propagated] == [(world["u1"], "category_id")]


def test_propagate_label_conflict_skipped(db, world):
    _later(db, lambda rev: fd.save_unit(db, rev, {"label": "5001", "category_id": world["a"]}, None))
    d = fd.open_draft(db, D, None)
    taken = fd.save_unit(db, d.rev, {"label": "5001", "category_id": world["a"]}, None)
    free = fd.save_unit(db, d.rev, {"label": "5002", "category_id": world["a"], "flags": [world["flag"]]}, None)
    res = fd.publish(db, None)
    later = fund_on(db, L)
    assert taken not in later.units and free in later.units
    assert later.units[free].flags == {world["flag"]}
    assert taken in fund_on(db, D).units
    assert [(s["entity"], s["id"], s["valid_from"]) for s in res.skipped] == [("unit", taken, L.isoformat())]
    assert "5001" in res.skipped[0]["reason"]
    assert ("unit", free, None) in {(p["entity"], p["id"], p["field"]) for p in res.propagated}


def test_propagate_retire_and_flag(db, world):
    """Выведенный в черновике объект выводится из поздней версии, если она его не меняла;
    снятый флаг снимается и там."""
    _later(db, lambda rev: fd.save_unit(db, rev, {"floor": "5"}, world["u2"]))
    d = fd.open_draft(db, D, None)
    fd.set_flag(db, d.rev, world["flag"], [world["u1"]], False)
    fd.retire_unit(db, d.rev, world["u2"])
    res = fd.publish(db, None)
    assert _unit(db, L, world["u1"]).flags == set()
    assert _unit(db, L, world["u2"]) is not None                # поздняя версия меняла объект — оставлен
    assert [(k["id"], k["field"]) for k in res.kept] == [(world["u2"], None)]

    d = fd.open_draft(db, D, None)                              # объект, который поздняя версия не меняла
    fd.retire_unit(db, d.rev, world["u1"])
    fd.publish(db, None)
    assert _unit(db, L, world["u1"]) is None


def test_propagate_false_leaves_later_versions(db, world):
    _later(db, lambda rev: fd.save_unit(db, rev, {"floor": "5"}, world["u2"]))
    d = fd.open_draft(db, D, None)
    fd.save_unit(db, d.rev, {"floor": "7"}, world["u1"])
    res = fd.publish(db, None, propagate=False)
    assert _unit(db, L, world["u1"]).floor == "4"
    assert _unit(db, D, world["u1"]).floor == "7"
    assert res.propagated == res.kept == res.skipped == []


def test_move_draft_across_later_version_409(db, world):
    """Сдвиг даты черновика за другую версию сменил бы базу — 409; внутри интервала базы — можно."""
    _later(db, lambda rev: fd.save_unit(db, rev, {"floor": "5"}, world["u2"]))
    d = fd.open_draft(db, D, None)
    fd.save_unit(db, d.rev, {"floor": "7"}, world["u1"])
    with pytest.raises(FundConflict, match="между датами есть другая версия"):
        fd.move_draft_date(db, d.rev, L + dt.timedelta(days=1))
    fd.move_draft_date(db, d.rev, D + dt.timedelta(days=10))      # та же база V0
    assert fd.current_draft(db).valid_from == D + dt.timedelta(days=10)


def test_move_same_date_draft_before_its_version_409(db, world):
    """Черновик на дату поздней версии (её замена) нельзя увести раньше неё: база стала бы другой."""
    _later(db, lambda rev: None)
    d = fd.open_draft(db, L, None)
    with pytest.raises(FundConflict, match="между датами"):
        fd.move_draft_date(db, d.rev, D)
    fd.move_draft_date(db, d.rev, L + dt.timedelta(days=3))
    fd.publish(db, None)


# ── предпросмотр и перевод броней (через API) ──────────────────────────────

TODAY = "2036-01-10"
DAY = "2036-02-01"
TABLES = ("stays_reservations", "stays_moves", "stays_assignments", "stays_fund_versions",
          "stays_category_states", "stays_group_states", "stays_unit_states", "stays_unit_state_flags",
          "stays_unit_lineage", "stays_units", "stays_categories")


def dump(db) -> dict:
    db.expire_all()
    db.rollback()
    out = {t: sorted(map(tuple, db.execute(text(f"SELECT * FROM {t}")).all()), key=repr) for t in TABLES}
    out["audit"] = db.scalar(select(func.count(AuditLog.id)))
    return out


def _connect_split(setup, mgr):
    """Коннекты K1, K2 и Делюкс без объектов; две брони коннекта 05–08.02 и одна живущая 28.01–06.02.
    Черновик с 01.02 делит K1 на два Делюкса — одной брони коннекта после 01.02 объекта нет."""
    conn = make_category(setup, n_units=2)
    dlx = make_category(setup, n_units=0)
    r1 = create_res(mgr, conn, "2036-02-05", "2036-02-08")
    r2 = create_res(mgr, conn, "2036-02-05", "2036-02-08")
    live = create_res(mgr, conn, "2036-01-28", "2036-01-31")
    opened = setup.post(f"{API}/fund/draft", json={"valid_from": DAY})
    assert opened.status_code == 200, opened.text
    k1 = conn["units"][0]["id"]
    split = setup.post(f"{API}/fund/draft/units/{k1}/split", json={
        "rev": opened.json()["rev"], "parts": [{"label": conn["code"] + "-a", "category_id": dlx["id"]},
                                               {"label": conn["code"] + "-b", "category_id": dlx["id"]}]})
    assert split.status_code == 200, split.text
    return conn, dlx, (r1, r2, live), split.json()["rev"]


def _publish(c, body, preview: bool):
    resp = c.post(f"{API}/fund/draft/publish", params={"preview": 1} if preview else {}, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_preview_lists_unassigned_after_connect_split(manager_role_client, manager_client, today, db):
    today(TODAY)
    conn, dlx, (r1, r2, _), rev = _connect_split(manager_role_client, manager_client)
    out = _publish(manager_role_client, {"rev": rev}, preview=True)
    assert out["preview"] is True
    res = out["result"]
    unassigned = res["affected"]["unassigned"]
    assert len(unassigned) == 1 and unassigned[0]["reservation_id"] in (r1["id"], r2["id"])
    assert [e["kind"] for e in res["fund_diff"]["units"]].count("added") == 2
    assert any(m["to_unit"] is None and m["reservation_id"] == unassigned[0]["reservation_id"]
               for m in res["affected"]["moved"])
    assert res["affected"]["category_missing"] == [] and res["affected"]["pin_invalid"] == []
    assert fd.current_draft(db) is not None                      # предпросмотр ничего не публикует


def test_preview_equals_publish(manager_role_client, manager_client, today, db):
    today(TODAY)
    conn, dlx, (r1, r2, _), rev = _connect_split(manager_role_client, manager_client)
    body = {"rev": rev, "propagate": True, "transfers": [{"reservation_id": r2["id"], "category_id": dlx["id"]}]}
    pv = _publish(manager_role_client, body, preview=True)
    sv = _publish(manager_role_client, body, preview=False)
    assert pv["preview"] is True and sv["preview"] is False
    assert pv["result"] == sv["result"] and pv["diff"] == sv["diff"]
    assert pv["result"]["affected"]["unassigned"] == []          # переведённая бронь получила Делюкс


def test_preview_leaves_db_clean(manager_role_client, manager_client, today, db):
    today(TODAY)
    conn, dlx, (r1, r2, _), rev = _connect_split(manager_role_client, manager_client)
    before = dump(db)
    _publish(manager_role_client, {"rev": rev, "transfers": [{"reservation_id": r1["id"],
                                                              "category_id": dlx["id"]}]}, preview=True)
    assert dump(db) == before                                    # ни фонда, ни броней, ни журнала


def test_publish_preview_stale_rev_409(manager_role_client, manager_client, today):
    today(TODAY)
    *_, rev = _connect_split(manager_role_client, manager_client)
    resp = manager_role_client.post(f"{API}/fund/draft/publish", params={"preview": 1}, json={"rev": rev - 1})
    assert resp.status_code == 409


def _journal(db, rid: int) -> list[dict]:
    import json
    db.expire_all()
    return [json.loads(a.payload_json)["diff"] for a in db.scalars(
        select(AuditLog).where(AuditLog.target == f"reservation:{rid}").order_by(AuditLog.id))]


def test_transfer_whole_reservation(manager_role_client, manager_client, today, db):
    today(TODAY)
    conn, dlx, (r1, r2, _), rev = _connect_split(manager_role_client, manager_client)
    out = _publish(manager_role_client, {"rev": rev, "transfers": [{"reservation_id": r1["id"],
                                                                    "category_id": dlx["id"]}]}, preview=False)
    db.expire_all()
    r = db.get(Reservation, r1["id"])
    assert r.category_id == dlx["id"] and db.scalars(select(Move).where(Move.reservation_id == r.id)).all() == []
    assert _journal(db, r.id)[-1]["category_id"] == [conn["id"], dlx["id"]]
    assert out["result"]["affected"]["unassigned"] == []
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "stays_fund_version").order_by(AuditLog.id.desc()))
    assert f'"reservation_id": {r1["id"]}' in audit.payload_json   # перевод — и в аудите публикации


def test_transfer_live_reservation_adds_move(manager_role_client, manager_client, today, db):
    today(TODAY)
    conn, dlx = make_category(manager_role_client, n_units=1), make_category(manager_role_client, n_units=1)
    live = create_res(manager_client, conn, "2036-01-29", "2036-02-06")
    opened = manager_role_client.post(f"{API}/fund/draft", json={"valid_from": DAY})
    assert opened.status_code == 200, opened.text
    out = _publish(manager_role_client, {"rev": opened.json()["rev"], "transfers": [
        {"reservation_id": live["id"], "category_id": dlx["id"]}]}, preview=False)
    assert out["preview"] is False
    db.expire_all()
    r = db.get(Reservation, live["id"])
    assert r.category_id == conn["id"]                           # до D бронь в прежней категории
    assert [(m.move_date.isoformat(), m.category_id) for m in
            db.scalars(select(Move).where(Move.reservation_id == r.id))] == [(DAY, dlx["id"])]
    assert _journal(db, r.id)[-1]["moves"] == [[], [[DAY, dlx["id"]]]]


def test_transfer_reservation_ended_before_day_422(manager_role_client, manager_client, today):
    today(TODAY)
    conn, dlx, (_, _, live), rev = _connect_split(manager_role_client, manager_client)
    resp = manager_role_client.post(f"{API}/fund/draft/publish", json={
        "rev": rev, "transfers": [{"reservation_id": live["id"], "category_id": dlx["id"]}]})
    assert resp.status_code == 422


def test_transfer_group_journals_every_member(manager_role_client, manager_client, today, db):
    """Перевод брони группы переводит и остальных её членов — журнал «было → стало» у каждого."""
    today(TODAY)
    conn, dlx = make_category(manager_role_client, n_units=1), make_category(manager_role_client, n_units=1)
    gid = manager_client.post(f"{API}/groups", json={"title": "Семья"}).json()["id"]
    a = create_res(manager_client, conn, "2036-02-05", "2036-02-08", group_id=gid)
    b = create_res(manager_client, conn, "2036-02-05", "2036-02-08", group_id=gid)
    opened = manager_role_client.post(f"{API}/fund/draft", json={"valid_from": DAY})
    assert opened.status_code == 200, opened.text
    _publish(manager_role_client, {"rev": opened.json()["rev"], "transfers": [
        {"reservation_id": a["id"], "category_id": dlx["id"]}]}, preview=False)
    db.expire_all()
    for rid in (a["id"], b["id"]):
        assert db.get(Reservation, rid).category_id == dlx["id"]
        assert _journal(db, rid)[-1]["category_id"] == [conn["id"], dlx["id"]]


# ── предпросмотр: части «до/после» сравниваются по покрытию, а не по индексу ──


def _draft_floor(setup, unit_id: int, cat: dict, label: str, valid_from: str = DAY) -> int:
    """Черновик с valid_from, где у объекта меняется только этаж (на размещение не влияет)."""
    opened = setup.post(f"{API}/fund/draft", json={"valid_from": valid_from})
    assert opened.status_code == 200, opened.text
    r = setup.put(f"{API}/fund/draft/units/{unit_id}", json={
        "rev": opened.json()["rev"], "label": label, "category_id": cat["id"], "floor": "9"})
    assert r.status_code == 200, r.text
    return r.json()["rev"]


def _moved_of(out: dict, rid: int) -> list[dict]:
    return [m for m in out["result"]["affected"]["moved"] if m["reservation_id"] == rid]


def test_preview_pinned_booking_across_new_boundary_not_moved(manager_role_client, manager_client, today):
    today(TODAY)
    cat = make_category(manager_role_client, n_units=2)
    pin = cat["units"][1]
    r = create_res(manager_client, cat, "2036-01-28", "2036-02-06", pins={"0": pin["id"]})
    assert r["segments"][0]["unit_id"] == pin["id"]
    rev = _draft_floor(manager_role_client, cat["units"][0]["id"], cat, cat["units"][0]["label"])
    out = _publish(manager_role_client, {"rev": rev}, preview=True)
    assert _moved_of(out, r["id"]) == []


def test_preview_booking_across_new_and_later_boundary_not_moved(manager_role_client, manager_client, today):
    today(TODAY)
    cat = make_category(manager_role_client, n_units=2)
    u0, u1 = cat["units"]
    # поздняя версия с 15.02 уже есть: части после неё сдвинули бы индекс при новой границе 01.02
    rev = _draft_floor(manager_role_client, u1["id"], cat, u1["label"], valid_from="2036-02-15")
    _publish(manager_role_client, {"rev": rev}, preview=False)
    r = create_res(manager_client, cat, "2036-01-28", "2036-02-20")
    rev = _draft_floor(manager_role_client, u1["id"], cat, u1["label"] + "x")
    out = _publish(manager_role_client, {"rev": rev}, preview=True)
    assert _moved_of(out, r["id"]) == [], _moved_of(out, r["id"])


def test_preview_real_unit_change_at_boundary_one_row(manager_role_client, manager_client, today):
    today(TODAY)
    cat = make_category(manager_role_client, n_units=2)
    u0, u1 = cat["units"]
    r = create_res(manager_client, cat, "2036-01-28", "2036-02-06")
    was = r["segments"][0]["unit_id"]
    other = u1["id"] if was == u0["id"] else u0["id"]
    opened = manager_role_client.post(f"{API}/fund/draft", json={"valid_from": DAY})
    assert opened.status_code == 200, opened.text
    gone = manager_role_client.delete(f"{API}/fund/draft/units/{was}", params={"rev": opened.json()["rev"]})
    assert gone.status_code == 200, gone.text
    out = _publish(manager_role_client, {"rev": gone.json()["rev"]}, preview=True)
    rows = _moved_of(out, r["id"])
    assert len(rows) == 1, rows
    assert rows[0]["from_unit"] == was and rows[0]["to_unit"] == other and rows[0]["since"] == DAY
