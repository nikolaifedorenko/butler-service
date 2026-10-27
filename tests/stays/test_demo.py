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
