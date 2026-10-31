"""fund_versions: фонд на дату (спецификация stays-fund-versions §3.3)."""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import delete

from app.modules.stays.adapters.orm import (
    Category,
    CategoryState,
    FundGroup,
    FundVersion,
    GroupState,
    Unit,
    UnitState,
)
from app.modules.stays.application.fund_versions import (
    INITIAL_DATE,
    CategoryInfo,
    FundSnapshot,
    FundTimeline,
    UnitInfo,
    boundary_pos,
    category_exists,
    fund_for,
    fund_on,
    snapshot_of,
)
from app.modules.stays.domain import halfday

from .helpers import kind_id

D1, D2, D3 = dt.date(2097, 11, 15), dt.date(2097, 12, 10), dt.date(2098, 1, 5)


@pytest.fixture()
def world(db):
    """Три версии в далёком будущем (две опубликованы, третья — черновик) + постоянные id."""
    cat, unit = Category(), Unit()
    db.add_all([cat, unit])
    db.flush()
    versions = {}
    for key, d, status in (("a", D1, "published"), ("b", D2, "published"), ("c", D3, "draft")):
        v = FundVersion(valid_from=d, status=status, rev=1)
        db.add(v)
        db.flush()
        versions[key] = v
        db.add(CategoryState(version_id=v.id, category_id=cat.id, code=f"C{uuid.uuid4().hex[:6]}",
                             title=f"Кат {key}", kind_id=kind_id("room"), weight=1.5, escorted=True, sort_order=3))
        db.flush()
        db.add(UnitState(version_id=v.id, unit_id=unit.id, label=f"U{key}", category_id=cat.id, floor="2"))
    db.commit()
    yield {"cat": cat.id, "unit": unit.id, "v": versions}
    db.rollback()
    ids = [v.id for v in versions.values()]
    for model in (UnitState, GroupState, CategoryState):
        db.execute(delete(model).where(model.version_id.in_(ids)))
    db.execute(delete(FundVersion).where(FundVersion.id.in_(ids)))
    db.execute(delete(Unit).where(Unit.id == unit.id))
    db.execute(delete(Category).where(Category.id == cat.id))
    db.commit()


def test_fund_on_picks_latest_not_after_day(db, world):
    assert fund_on(db, D1).version_id == world["v"]["a"].id
    assert fund_on(db, D2 - dt.timedelta(days=1)).version_id == world["v"]["a"].id
    assert fund_on(db, D2).version_id == world["v"]["b"].id
    assert fund_on(db, dt.date(2098, 6, 1)).version_id == world["v"]["b"].id     # черновик не в счёт
    assert fund_on(db, dt.date(2020, 1, 1)).valid_from == INITIAL_DATE


def test_timeline_two_versions_in_month(db, world):
    tl = fund_for(db, dt.date(2097, 12, 1), dt.date(2097, 12, 31))
    assert tl.boundaries() == [D2]
    assert tl.on(dt.date(2097, 12, 9)).categories[world["cat"]].title == "Кат a"
    assert tl.on(D2).categories[world["cat"]].title == "Кат b"
    assert [s.version_id for s in tl.snapshots()] == [world["v"]["a"].id, world["v"]["b"].id]
    c = tl.on(D2).categories[world["cat"]]
    assert (c.weight, c.escorted, c.sort_order) == (1.5, True, 3)
    assert tl.on(D2).units[world["unit"]].flags == frozenset()


def test_boundary_is_pm_of_day():
    assert boundary_pos(D2) == halfday.pos(D2, halfday.PM)
    assert halfday.pos(D2, halfday.AM) < boundary_pos(D2)


def test_draft_not_visible_in_timeline(db, world):
    tl = fund_for(db, dt.date(2097, 12, 1), dt.date(2098, 2, 28))
    assert world["v"]["c"].id not in [s.version_id for s in tl.snapshots()]
    assert tl.boundaries() == [D2]
    assert snapshot_of(db, world["v"]["c"].id).units[world["unit"]].label == "Uc"   # а напрямую — виден


def test_branch_and_paths(db, world):
    vid = world["v"]["a"].id
    g = [FundGroup() for _ in range(4)]
    db.add_all(g)
    db.flush()
    corp, block, sea, other = (x.id for x in g)
    db.add(GroupState(version_id=vid, group_id=corp, parent_id=None, title="Корпус", sort_order=1))
    db.flush()
    db.add_all([GroupState(version_id=vid, group_id=block, parent_id=corp, title="Блок B", sort_order=1),
                GroupState(version_id=vid, group_id=other, parent_id=corp, title="Блок C", sort_order=2)])
    db.flush()
    db.add(GroupState(version_id=vid, group_id=sea, parent_id=block, title="Вид на море", sort_order=1))
    db.commit()
    try:
        snap = snapshot_of(db, vid)
        assert snap.groups[sea].path == (corp, block, sea)
        assert snap.branch(block) == {block, sea}
        assert snap.branch(corp) == {corp, block, sea, other}
        assert snap.branch(sea) == {sea}
        assert snap.path_titles(sea) == ("Корпус", "Блок B", "Вид на море")
    finally:
        db.rollback()
        db.execute(delete(GroupState).where(GroupState.version_id == vid,
                                            GroupState.group_id.in_([sea, other])))
        db.execute(delete(GroupState).where(GroupState.version_id == vid, GroupState.group_id == block))
        db.execute(delete(GroupState).where(GroupState.version_id == vid, GroupState.group_id == corp))
        db.execute(delete(FundGroup).where(FundGroup.id.in_([corp, block, sea, other])))
        db.commit()


def test_fund_for_query_budget(db, world, sql_counter):
    with sql_counter() as c:
        tl = fund_for(db, dt.date(2097, 11, 1), dt.date(2098, 2, 28))
    assert len(tl.snapshots()) == 3      # начальная, a, b; c — черновик
    assert c["total"] <= 6, c["by_statement"]


def test_category_exists(db, world):
    assert category_exists(db, world["cat"])
    assert not category_exists(db, 10**9)


def _snap(vid: int, d: dt.date, units: dict[int, str], cats: dict[int, str]) -> FundSnapshot:
    return FundSnapshot(vid, d, {c: CategoryInfo(c, code, code, 1, 1.0, False, 0) for c, code in cats.items()},
                        {}, {u: UnitInfo(u, label, 1, None, "", frozenset()) for u, label in units.items()})


def test_timeline_unit_and_category_on_day_with_fallback():
    """Состояние на день; нет в фонде дня — ближайшее: сначала раньше, затем позже; нет нигде — None."""
    a, b, c = dt.date(2090, 1, 1), dt.date(2090, 2, 1), dt.date(2090, 3, 1)
    tl = FundTimeline([(a, _snap(1, a, {10: "4003", 11: "старый"}, {1: "DTG"})),
                       (b, _snap(2, b, {10: "4103"}, {1: "DKG", 2: "NEW"})),
                       (c, _snap(3, c, {10: "4103", 12: "новый"}, {1: "DKG"}))])
    assert tl.unit(10, a).label == "4003" and tl.unit(10, b).label == "4103"
    assert tl.unit(10, a - dt.timedelta(days=5)).label == "4003"        # до первой загруженной версии
    assert tl.unit(10, c + dt.timedelta(days=99)).label == "4103"       # после последней
    assert tl.unit(11, c).label == "старый"                              # выведен — прежнее состояние
    assert tl.unit(12, a).label == "новый"                               # ещё не заведён — позднее состояние
    assert tl.unit(99, b) is None and tl.unit(None, b) is None
    assert tl.category(1, a).code == "DTG" and tl.category(1, c).code == "DKG"
    assert tl.category(2, c).code == "NEW" and tl.category(2, a).code == "NEW"
    assert tl.category(3, a) is None
    assert tl.boundaries() == [b, c] and tl.on(b + dt.timedelta(days=3)).version_id == 2
