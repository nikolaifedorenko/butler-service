"""Шахматка, задача 19: демо-данные (§11) — весь фонд, гости, брони, примеры предупреждений."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select


def test_demo_fund_and_warnings(db):
    from app.core.time import local_date
    from app.modules.stays.adapters.duty_timesheet import TimesheetDuty
    from app.modules.stays.adapters.orm import Guest, GuestLink, Reservation
    from app.modules.stays.application.context import load_context
    from app.modules.stays.application.fund_versions import INITIAL_DATE, fund_on

    fund = fund_on(db, INITIAL_DATE)
    codes = ("VEG", "FWV", "VIG", "ESTATE", "MED", "DLX", "PRM", "FAM", "JST", "SUI", "PRS")
    cats = {c.id for c in fund.categories.values() if c.code in codes}
    assert len(cats) == 11
    assert sum(1 for u in fund.units.values() if u.category_id in cats) == 440
    assert db.scalar(select(func.count(Guest.id)).where(Guest.source == "demo")) >= 60
    assert db.scalar(select(func.count(Guest.id)).where(Guest.source == "demo", Guest.level == "vvip")) == 2
    assert db.scalar(select(func.count(GuestLink.id))) >= 5
    res = list(db.scalars(select(Reservation).where(Reservation.source == "demo")))
    assert len(res) >= 300
    assert {r.status for r in res} >= {"confirmed", "in_house", "no_show"}
    assert any(r.group_id for r in res) and any(r.declined_butler for r in res)
    today = local_date()
    ctx = load_context(db, today, today + dt.timedelta(days=29), TimesheetDuty(db))
    kinds = {w.kind for d in ctx.days() for w in ctx.warnings(d)}
    assert {"overload", "off_shift", "need_replacement", "hole"} <= kinds


def test_demo_idempotent(db):
    from app.modules.stays.adapters.orm import Category
    from app.modules.stays.application.demo import seed_stays_demo
    before = db.scalar(select(func.count(Category.id)))
    seed_stays_demo(db)
    assert db.scalar(select(func.count(Category.id))) == before


def _node(fund, *path):
    ids = [g.id for g in fund.groups.values() if fund.path_titles(g.id) == path]
    return ids[0] if ids else None


def test_demo_has_tree(db):
    from app.core.time import local_date
    from app.modules.stays.application.fund_versions import fund_on

    fund = fund_on(db, local_date())
    villas = _node(fund, "Винные виллы", "Семейная", "Первая линия")
    sea = _node(fund, "Корпус", "Блок B", "Вид на море")
    assert villas and sea
    assert any(u.group_id == villas for u in fund.units.values())
    assert any(u.group_id == sea for u in fund.units.values())
    demo = {c.id for c in fund.categories.values() if c.code in ("VEG", "DLX", "MED", "ESTATE")}
    assert all(u.group_id is not None for u in fund.units.values() if u.category_id in demo)


def test_demo_has_flags(db):
    from app.core.time import local_date
    from app.modules.stays.adapters.orm import UnitFlag
    from app.modules.stays.application.fund_versions import fund_on

    fund = fund_on(db, local_date())
    titles = {f.id: f.title for f in db.scalars(select(UnitFlag))}
    used = {titles[f] for u in fund.units.values() for f in u.flags}
    assert len(used) >= 3 and "Смежные номера" in used


def test_demo_future_version_splits_connect(db):
    """Будущую версию демо заводит seed_connect_split; conftest снимает её на время прогона
    (см. _demo_without_future_version), поэтому здесь она создаётся и убирается."""
    from app.core.time import local_date
    from app.modules.stays.adapters.orm import FundVersion, UnitLineage
    from app.modules.stays.application import fund_drafts
    from app.modules.stays.application.demo import seed_connect_split
    from app.modules.stays.application.fund_versions import fund_on

    day = local_date() + dt.timedelta(days=14)
    now = fund_on(db, local_date())
    seed_connect_split(db)
    db.commit()
    try:
        vid = db.scalar(select(FundVersion.id).where(FundVersion.status == "published",
                                                     FundVersion.valid_from == day))
        assert vid is not None
        later = fund_on(db, day)
        old = next(u.id for u in now.units.values() if u.label == "12134")
        assert old not in later.units
        new = {u.label: u for u in later.units.values() if u.label in ("1213", "1214")}
        assert set(new) == {"1213", "1214"}
        dlx = next(c.id for c in later.categories.values() if c.code == "DLX")
        assert all(u.category_id == dlx for u in new.values())
        lineage = {r.unit_id: r.predecessor_id for r in db.scalars(select(UnitLineage))}
        assert all(lineage[u.id] == old for u in new.values())
        assert all(u.flags == now.units[old].flags and u.flags for u in new.values())   # флаги унаследованы
        assert not any(u.label in ("1213", "1214") for u in now.units.values())
    finally:
        fund_drafts.delete_version(db, vid)
        db.commit()


def test_seed_initial_refuses_filled_version(db):
    import pytest

    from app.modules.stays.application import fund_drafts
    from app.modules.stays.application.fund import FundConflict

    with pytest.raises(FundConflict):
        fund_drafts.seed_initial(db, [], [], [], [])
