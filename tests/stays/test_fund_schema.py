"""Версии фонда: таблицы и ревизия 0010 (спецификация stays-fund-versions §3.2)."""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError

from app.core.db import SessionLocal, engine
from app.modules.stays.adapters.orm import (
    Category,
    CategoryState,
    FundGroup,
    FundVersion,
    GroupState,
    StaysSettings,
    Unit,
    UnitFlag,
    UnitState,
    UnitStateFlag,
)

_D = dt.date(2099, 1, 1)


@pytest.fixture()
def version(db):
    """Своя версия-черновик в далёком будущем; снимается вместе с содержимым."""
    v = FundVersion(valid_from=_D, status="draft", rev=1)
    db.add(v)
    db.commit()
    created = {"cats": [], "units": [], "flags": [], "groups": []}
    yield v, created
    db.rollback()
    db.execute(delete(UnitStateFlag).where(UnitStateFlag.version_id == v.id))
    db.execute(delete(UnitState).where(UnitState.version_id == v.id))
    db.execute(delete(GroupState).where(GroupState.version_id == v.id))
    db.execute(delete(CategoryState).where(CategoryState.version_id == v.id))
    db.execute(delete(FundVersion).where(FundVersion.id == v.id))
    for model, key in ((UnitFlag, "flags"), (Unit, "units"), (FundGroup, "groups"), (Category, "cats")):
        for i in created[key]:
            db.execute(delete(model).where(model.id == i))
    db.commit()


def _cat(db, created, vid, code=None):
    c = Category()
    db.add(c)
    db.flush()
    created["cats"].append(c.id)
    db.add(CategoryState(version_id=vid, category_id=c.id, code=code or uuid.uuid4().hex[:8],
                         title="Кат", kind="room", weight=1, escorted=False, sort_order=1))
    db.flush()
    return c.id


def _unit(db, created):
    u = Unit()
    db.add(u)
    db.flush()
    created["units"].append(u.id)
    return u.id


def test_initial_version_exists(db):
    v = db.scalar(select(FundVersion).where(FundVersion.valid_from == dt.date(2000, 1, 1)))
    assert v is not None and v.status == "published"
    assert db.scalar(select(StaysSettings.in_production).where(StaysSettings.id == 1)) in (False, None, 0)


def test_label_unique_in_version(db, version):
    v, created = version
    cat = _cat(db, created, v.id)
    db.commit()
    u1, u2 = _unit(db, created), _unit(db, created)
    db.add(UnitState(version_id=v.id, unit_id=u1, label="X1", category_id=cat, floor=""))
    db.commit()
    db.add(UnitState(version_id=v.id, unit_id=u2, label="X1", category_id=cat, floor=""))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    other = FundVersion(valid_from=dt.date(2099, 2, 1), status="draft", rev=1)
    db.add(other)
    db.flush()
    try:
        c2 = _cat(db, created, other.id)
        db.add(UnitState(version_id=other.id, unit_id=u2, label="X1", category_id=c2, floor=""))
        db.commit()      # то же обозначение в другой версии — можно
    finally:
        db.rollback()
        db.execute(delete(UnitState).where(UnitState.version_id == other.id))
        db.execute(delete(CategoryState).where(CategoryState.version_id == other.id))
        db.execute(delete(FundVersion).where(FundVersion.id == other.id))
        db.commit()


def test_code_unique_in_version(db, version):
    v, created = version
    _cat(db, created, v.id, code="DUP")
    db.commit()
    with pytest.raises(IntegrityError):
        _cat(db, created, v.id, code="DUP")
        db.commit()
    db.rollback()


def test_unit_state_category_must_be_in_same_version(db, version):
    v, created = version
    other = FundVersion(valid_from=dt.date(2099, 3, 1), status="draft", rev=1)
    db.add(other)
    db.flush()
    try:
        foreign_cat = _cat(db, created, other.id)
        u = _unit(db, created)
        db.commit()
        db.add(UnitState(version_id=v.id, unit_id=u, label="Y1", category_id=foreign_cat, floor=""))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.execute(delete(CategoryState).where(CategoryState.version_id == other.id))
        db.execute(delete(FundVersion).where(FundVersion.id == other.id))
        db.commit()


def test_used_flag_restrict(db, version):
    v, created = version
    cat = _cat(db, created, v.id)
    u = _unit(db, created)
    flag = UnitFlag(title=f"f-{uuid.uuid4().hex[:6]}", color="#fff", sort_order=1, archived=False)
    db.add(flag)
    db.flush()
    created["flags"].append(flag.id)
    db.add(UnitState(version_id=v.id, unit_id=u, label="Z1", category_id=cat, floor=""))
    db.flush()
    db.add(UnitStateFlag(version_id=v.id, unit_id=u, flag_id=flag.id))
    db.commit()
    with pytest.raises(IntegrityError):
        db.execute(delete(UnitFlag).where(UnitFlag.id == flag.id))
        db.commit()
    db.rollback()
    # удаление объекта в версии уносит его флаги
    db.delete(db.get(UnitState, (v.id, u)))
    db.commit()
    assert db.scalar(select(UnitStateFlag).where(UnitStateFlag.version_id == v.id)) is None


def test_downgrade_restores_columns(db):
    """upgrade → downgrade → upgrade: колонки возвращаются в Category/Unit и уходят обратно."""
    from alembic import command

    from app.bootstrap.schema_version import config

    db.rollback()
    db.close()
    command.downgrade(config(), "0009")
    try:
        cols = {c["name"] for c in inspect(engine).get_columns("stays_units")}
        assert {"label", "category_id", "building", "floor", "active", "sort_order"} <= cols
        assert "title" in {c["name"] for c in inspect(engine).get_columns("stays_categories")}
        assert "stays_fund_versions" not in inspect(engine).get_table_names()
    finally:
        command.upgrade(config(), "head")
    assert {c["name"] for c in inspect(engine).get_columns("stays_units")} == {"id"}
    with SessionLocal() as s:
        assert s.scalar(select(FundVersion).where(FundVersion.valid_from == dt.date(2000, 1, 1))) is not None


def test_downgrade_refuses_with_several_versions(db, version, monkeypatch):
    from alembic import command

    from app.bootstrap.schema_version import config

    monkeypatch.delenv("STAYS_FUND_DOWNGRADE_FORCE", raising=False)
    db.rollback()
    db.close()
    with pytest.raises(RuntimeError, match="0010"):
        command.downgrade(config(), "0009")
    assert inspect(engine).has_table("stays_fund_versions")
