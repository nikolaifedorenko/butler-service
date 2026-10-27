"""fund_drafts: черновик фонда, действия и публикация (спецификация stays-fund-versions §4)."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import delete, func, select

from app.core.audit import AuditLog
from app.modules.stays.adapters.orm import (
    Category,
    CategoryState,
    FundGroup,
    FundVersion,
    GroupState,
    Unit,
    UnitFlag,
    UnitLineage,
    UnitState,
    UnitStateFlag,
)
from app.modules.stays.application import fund_drafts as fd
from app.modules.stays.application.fund import FundConflict, FundError
from app.modules.stays.application.fund_versions import fund_on, snapshot_of

V0 = dt.date(2093, 1, 1)          # опубликованная версия-основа
NOW = "2093-01-10"
D = dt.date(2093, 2, 1)           # дата черновика в тестах
LO, HI = dt.date(2093, 1, 1), dt.date(2095, 1, 1)


pytestmark = pytest.mark.usefixtures("no_allocation")


@pytest.fixture()
def world(db, today):
    """Основа V0: категории A и B, узлы Корпус → Этаж, объекты 4003 (A, Этаж, флаг) и 4004 (B)."""
    today(NOW)
    max_unit = db.scalar(select(func.coalesce(func.max(Unit.id), 0)))
    max_cat = db.scalar(select(func.coalesce(func.max(Category.id), 0)))
    max_grp = db.scalar(select(func.coalesce(func.max(FundGroup.id), 0)))
    flag = UnitFlag(title=f"тест-флаг-{max_unit}")
    a, b, g1, g2, u1, u2 = Category(), Category(), FundGroup(), FundGroup(), Unit(), Unit()
    db.add_all([flag, a, b, g1, g2, u1, u2])
    db.flush()
    v = FundVersion(valid_from=V0, status="published", rev=1)
    db.add(v)
    db.flush()
    db.add_all([CategoryState(version_id=v.id, category_id=a.id, code="TA", title="Кат А"),
                CategoryState(version_id=v.id, category_id=b.id, code="TB", title="Кат Б")])
    db.add(GroupState(version_id=v.id, group_id=g1.id, parent_id=None, title="Корпус"))
    db.flush()
    db.add(GroupState(version_id=v.id, group_id=g2.id, parent_id=g1.id, title="Этаж"))
    db.flush()
    db.add_all([UnitState(version_id=v.id, unit_id=u1.id, label="4003", category_id=a.id, group_id=g2.id, floor="4"),
                UnitState(version_id=v.id, unit_id=u2.id, label="4004", category_id=b.id, group_id=g1.id, floor="4")])
    db.flush()
    db.add(UnitStateFlag(version_id=v.id, unit_id=u1.id, flag_id=flag.id))
    db.commit()
    yield {"v0": v.id, "a": a.id, "b": b.id, "g1": g1.id, "g2": g2.id, "u1": u1.id, "u2": u2.id, "flag": flag.id}
    db.rollback()
    ids = list(db.scalars(select(FundVersion.id).where(FundVersion.valid_from >= LO, FundVersion.valid_from < HI)))
    db.execute(update_null_base(ids))
    db.execute(delete(UnitLineage).where(UnitLineage.version_id.in_(ids)))
    for model in (UnitStateFlag, UnitState, GroupState, CategoryState):
        db.execute(delete(model).where(model.version_id.in_(ids)))
    db.execute(delete(FundVersion).where(FundVersion.id.in_(ids)))
    db.execute(delete(UnitFlag).where(UnitFlag.title.like("тест-флаг-%")))
    db.execute(delete(Unit).where(Unit.id > max_unit))
    db.execute(delete(Category).where(Category.id > max_cat))
    db.execute(delete(FundGroup).where(FundGroup.id > max_grp))
    db.execute(delete(AuditLog).where(AuditLog.action == "stays_fund_version", AuditLog.actor_name == "system"))
    db.commit()


def update_null_base(ids):
    from sqlalchemy import update
    return update(FundVersion).where(FundVersion.base_version_id.in_(ids)).values(base_version_id=None)


def _open(db, day=D):
    return fd.open_draft(db, day, None)


def _exact(exc, cls):
    return type(exc.value) is cls


def test_open_draft_in_past_422(db, world):
    with pytest.raises(FundError) as e:
        _open(db, dt.date(2093, 1, 9))
    assert _exact(e, FundError)


def test_second_draft_409(db, world):
    _open(db)
    with pytest.raises(FundConflict):
        _open(db, dt.date(2093, 3, 1))


def test_rev_mismatch_409(db, world):
    d = _open(db)
    fd.save_unit(db, d.rev, {"floor": "5"}, world["u1"])
    with pytest.raises(FundConflict):
        fd.save_unit(db, d.rev - 1, {"floor": "6"}, world["u1"])      # устаревший rev
    assert d.rev == 2


def test_change_category_of_unit_keeps_id(db, world):
    d = _open(db)
    uid = fd.save_unit(db, d.rev, {"category_id": world["b"]}, world["u1"])
    assert uid == world["u1"]
    assert snapshot_of(db, d.id).units[uid].category_id == world["b"]
    assert snapshot_of(db, world["v0"]).units[uid].category_id == world["a"]


def test_rename_category_code_keeps_id(db, world):
    d = _open(db)
    cid = fd.save_category(db, d.rev, {"code": "DKG"}, world["a"])
    assert cid == world["a"]
    assert snapshot_of(db, d.id).categories[cid].code == "DKG"
    assert snapshot_of(db, d.id).categories[cid].title == "Кат А"
    with pytest.raises(FundConflict):                      # код занят другой категорией
        fd.save_category(db, d.rev, {"code": "TB"}, world["a"])


def test_change_label_from_date(db, world):
    d = _open(db)
    fd.save_unit(db, d.rev, {"label": "4103"}, world["u1"])
    fd.publish(db, None)
    u = world["u1"]
    assert fund_on(db, D - dt.timedelta(days=1)).units[u].label == "4003"
    assert fund_on(db, D).units[u].label == "4103"


def test_split_creates_lineage(db, world):
    d = _open(db)
    ids = fd.split_unit(db, d.rev, world["u1"], [{"label": "4003A"}, {"label": "4003B", "floor": "5"}])
    snap = snapshot_of(db, d.id)
    assert world["u1"] not in snap.units
    assert [snap.units[i].label for i in ids] == ["4003A", "4003B"]
    assert snap.units[ids[0]].group_id == world["g2"] and snap.units[ids[0]].floor == "4"
    assert snap.units[ids[0]].flags == {world["flag"]} and snap.units[ids[1]].floor == "5"
    pairs = set(db.execute(select(UnitLineage.unit_id, UnitLineage.predecessor_id)
                           .where(UnitLineage.version_id == d.id)).all())
    assert pairs == {(i, world["u1"]) for i in ids}


def test_merge_mixed_groups_requires_choice(db, world):
    d = _open(db)
    with pytest.raises(FundError):                         # разные узлы и категории, выбора нет
        fd.merge_units(db, d.rev, [world["u1"], world["u2"]], {"label": "4003-4"})
    with pytest.raises(FundError):                         # узел выбран, категория — нет
        fd.merge_units(db, d.rev, [world["u1"], world["u2"]], {"label": "M", "group_id": world["g1"]})
    new = fd.merge_units(db, d.rev, [world["u1"], world["u2"]],
                         {"label": "4003-4", "group_id": world["g1"], "category_id": world["a"]})
    snap = snapshot_of(db, d.id)
    assert set(snap.units) == {new} and snap.units[new].flags == {world["flag"]}
    assert set(db.scalars(select(UnitLineage.predecessor_id).where(UnitLineage.unit_id == new))) \
        == {world["u1"], world["u2"]}


def test_retire_category_with_units_409(db, world):
    d = _open(db)
    with pytest.raises(FundConflict):
        fd.retire_category(db, d.rev, world["a"])
    fd.retire_unit(db, d.rev, world["u1"])
    fd.retire_category(db, d.rev, world["a"])
    assert world["a"] not in snapshot_of(db, d.id).categories


def test_retire_group_with_units_or_children_409(db, world):
    d = _open(db)
    with pytest.raises(FundConflict):
        fd.retire_group(db, d.rev, world["g1"])            # подузел и объект
    with pytest.raises(FundConflict):
        fd.retire_group(db, d.rev, world["g2"])            # объект
    fd.retire_unit(db, d.rev, world["u1"])
    fd.retire_group(db, d.rev, world["g2"])
    assert world["g2"] not in snapshot_of(db, d.id).groups


def test_group_cycle_422(db, world):
    d = _open(db)
    for gid, parent in ((world["g1"], world["g2"]), (world["g1"], world["g1"])):
        with pytest.raises(FundError) as e:
            fd.save_group(db, d.rev, {"parent_id": parent}, gid)
        assert _exact(e, FundError)
    new = fd.save_group(db, d.rev, {"title": "Новый", "parent_id": world["g2"]}, None)
    assert snapshot_of(db, d.id).groups[new].path == (world["g1"], world["g2"], new)


def test_flag_from_date(db, world):
    d = _open(db)
    fd.set_flag(db, d.rev, world["flag"], [world["u2"]], True)
    fd.set_flag(db, d.rev, world["flag"], [world["u1"]], False)
    fd.publish(db, None)
    before, after = fund_on(db, D - dt.timedelta(days=1)), fund_on(db, D)
    assert before.units[world["u1"]].flags == {world["flag"]} and before.units[world["u2"]].flags == set()
    assert after.units[world["u1"]].flags == set() and after.units[world["u2"]].flags == {world["flag"]}


def test_draft_on_existing_version_date_replaces_it(db, world):
    d = _open(db)
    fd.save_unit(db, d.rev, {"floor": "7"}, world["u1"])
    first = fd.publish(db, None)
    d2 = _open(db, D)                                     # правка «с той же даты»
    assert d2.valid_from == D and d2.base_version_id == first.id
    assert snapshot_of(db, d2.id).units[world["u1"]].floor == "7"
    fd.save_unit(db, d2.rev, {"floor": "8", "label": "4003x"}, world["u1"])
    second = fd.publish(db, None)
    assert second.id == first.id and fd.current_draft(db) is None
    assert db.scalar(select(func.count()).select_from(FundVersion).where(FundVersion.valid_from == D)) == 1
    u = fund_on(db, D).units[world["u1"]]
    assert (u.floor, u.label) == ("8", "4003x")
    assert fund_on(db, D - dt.timedelta(days=1)).units[world["u1"]].floor == "4"


def test_publish_stale_draft_date_409(db, world, today):
    d = _open(db, dt.date(2093, 1, 11))                   # «завтра»
    today("2093-01-12")                                   # «сегодня» — послезавтра
    with pytest.raises(FundConflict, match="сдвиньте"):
        fd.publish(db, None)
    fd.move_draft_date(db, d.rev, dt.date(2093, 1, 12))
    assert fd.publish(db, None).valid_from == dt.date(2093, 1, 12)


def test_publish_writes_audit(db, world):
    d = _open(db)
    fd.save_unit(db, d.rev, {"label": "4103"}, world["u1"])
    v = fd.publish(db, None)
    db.flush()
    row = db.scalar(select(AuditLog).where(AuditLog.action == "stays_fund_version").order_by(AuditLog.id.desc()))
    assert row.target == f"fund_version:{v.id}" and "4103" in row.payload_json


def test_diff_kinds(db, world):
    d = _open(db)
    fd.save_unit(db, d.rev, {"label": "4103"}, world["u1"])
    fd.retire_unit(db, d.rev, world["u2"])
    new = fd.save_unit(db, d.rev, {"label": "9", "category_id": world["a"]}, None)
    fd.set_flag(db, d.rev, world["flag"], [new], True)
    out = fd.diff(db, world["v0"], d.id)
    kinds = {e["id"]: e["kind"] for e in out.units}
    assert kinds == {world["u1"]: "changed", world["u2"]: "retired", new: "added"}
    assert out.categories == [] and out.groups == [] and out.flags == []


def test_delete_current_version_409(db, world):
    with pytest.raises(FundConflict):
        fd.delete_version(db, world["v0"])                # действующая
    first = db.scalar(select(FundVersion.id).order_by(FundVersion.valid_from).limit(1))
    with pytest.raises(FundConflict):
        fd.delete_version(db, first)                      # исходная


def test_delete_future_version_ok(db, world):
    d = _open(db)
    v = fd.publish(db, None)
    fd.delete_version(db, v.id)
    assert db.get(FundVersion, v.id) is None
    d2 = _open(db, dt.date(2093, 3, 1))                   # черновик тоже удаляется
    fd.delete_version(db, d2.id)
    assert fd.current_draft(db) is None
    assert d.id  # публикация переиспользовала строку черновика


def test_delete_used_flag_409_archive_ok(db, world):
    with pytest.raises(FundConflict):
        fd.delete_flag(db, world["flag"])
    fd.archive_flag(db, world["flag"], True)
    assert db.get(UnitFlag, world["flag"]).archived is True
    d = _open(db)
    with pytest.raises(FundError):                        # архивный флаг не ставится
        fd.set_flag(db, d.rev, world["flag"], [world["u2"]], True)
    free = fd.save_flag(db, {"title": "тест-флаг-свободный"}, None)
    fd.delete_flag(db, free)
    assert db.get(UnitFlag, free) is None


def test_delete_version_under_draft_409(db, world):
    d = _open(db)
    v = fd.publish(db, None)
    d2 = _open(db, D)                                     # черновик опирается на v
    assert d2.base_version_id == v.id
    with pytest.raises(FundConflict, match="черновик"):
        fd.delete_version(db, v.id)
    fd.delete_version(db, d2.id)
    fd.delete_version(db, v.id)
    assert d.id


def test_split_and_merge_keep_archived_flag(db, world):
    fd.archive_flag(db, world["flag"], True)
    d = _open(db)
    a, b = fd.split_unit(db, d.rev, world["u1"], [{"label": "S1"}, {"label": "S2"}])
    assert snapshot_of(db, d.id).units[a].flags == {world["flag"]}
    m = fd.merge_units(db, d.rev, [a, b], {"label": "M1"})
    assert snapshot_of(db, d.id).units[m].flags == {world["flag"]}
    with pytest.raises(FundError):                        # а вот выбрать архивный флаг заново нельзя
        fd.save_unit(db, d.rev, {"label": "N", "category_id": world["a"], "flags": [world["flag"]]}, None)
