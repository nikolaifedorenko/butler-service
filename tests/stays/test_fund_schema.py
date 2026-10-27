"""Версии фонда: таблицы и ревизия 0010 (спецификация stays-fund-versions §3.2)."""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError

from app.core.db import engine
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
    other = FundVersion(valid_from=dt.date(2099, 2, 1), status="published", rev=1)
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
    other = FundVersion(valid_from=dt.date(2099, 3, 1), status="published", rev=1)
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


@pytest.fixture()
def iso_engine(tmp_path, monkeypatch):
    """Свежая SQLite-база на head: миграционные тесты откатывают схему и не должны зависеть от того,
    какие версии фонда опубликовали другие тесты в общей базе (0010 отказывает откат при >1 версии)."""
    from alembic import command
    from sqlalchemy import create_engine

    import app.core.db as core_db
    from app.bootstrap.schema_version import config

    eng = create_engine(f"sqlite:///{tmp_path / 'iso.db'}", future=True)
    monkeypatch.setattr(core_db, "engine", eng)          # env.py Alembic берёт engine из app.core.db
    command.upgrade(config(), "head")
    yield eng
    eng.dispose()


def test_downgrade_restores_columns(iso_engine):
    """upgrade → downgrade → upgrade: колонки возвращаются в Category/Unit и уходят обратно."""
    from alembic import command
    from sqlalchemy import text

    from app.bootstrap.schema_version import config

    engine = iso_engine
    command.downgrade(config(), "0009")
    try:
        cols = {c["name"] for c in inspect(engine).get_columns("stays_units")}
        assert {"label", "category_id", "building", "floor", "active", "sort_order"} <= cols
        assert "title" in {c["name"] for c in inspect(engine).get_columns("stays_categories")}
        assert "stays_fund_versions" not in inspect(engine).get_table_names()
    finally:
        command.upgrade(config(), "head")
    assert {c["name"] for c in inspect(engine).get_columns("stays_units")} == {"id"}
    with engine.connect() as c:
        assert c.execute(text("SELECT id FROM stays_fund_versions WHERE valid_from = '2000-01-01'")).first()


def test_downgrade_refuses_with_several_versions(db, version, monkeypatch):
    from alembic import command

    from app.bootstrap.schema_version import config

    monkeypatch.delenv("STAYS_FUND_DOWNGRADE_FORCE", raising=False)
    db.rollback()
    db.close()
    with pytest.raises(RuntimeError, match="0010"):
        command.downgrade(config(), "0009")
    assert inspect(engine).has_table("stays_fund_versions")


def test_migration_with_data_roundtrip(iso_engine):
    """0009 → 0010 → 0009 → 0010 на данных: категория, активные и неактивный объект, бронь с
    назначением. Исходная версия содержит ровно активные объекты; откат возвращает значения."""
    from alembic import command
    from sqlalchemy import text

    from app.bootstrap.schema_version import config

    engine = iso_engine
    command.downgrade(config(), "0009")
    try:
        with engine.begin() as c:
            c.execute(text("INSERT INTO stays_categories (id, code, title, kind, escorted, weight, sort_order) "
                           "VALUES (9001, 'MIG', 'Миграция', 'villa', 1, 4, 7)"))
            for uid, label, floor, active in ((9101, 'M-1', '2', 1), (9102, 'M-2', '', 1), (9103, 'M-OFF', '3', 0)):
                c.execute(text("INSERT INTO stays_units (id, label, category_id, building, floor, active, sort_order) "
                               "VALUES (:i, :l, 9001, 'B', :f, :a, 5)"), {"i": uid, "l": label, "f": floor, "a": active})
            c.execute(text("INSERT INTO stays_reservations (id, number, status, check_in, check_out, early, late, "
                           "category_id, paid_by, customer, purpose, note, declined_butler, fields_json, source, "
                           "version, search_text, created_at, updated_at) VALUES (9201, 'M1', 'confirmed', "
                           "'2099-01-01', '2099-01-03', 0, 0, 9001, '', '', '', '', 0, '{}', '', 1, '', "
                           "'2099-01-01 00:00:00', '2099-01-01 00:00:00')"))
            c.execute(text("INSERT INTO stays_assignments (reservation_id, seg_index, unit_id, pinned) "
                           "VALUES (9201, 0, 9101, 1)"))
        command.upgrade(config(), "head")
        with engine.connect() as c:
            v = c.execute(text("SELECT id FROM stays_fund_versions WHERE valid_from = '2000-01-01'")).scalar_one()
            units = c.execute(text("SELECT unit_id, label, category_id, group_id, floor FROM stays_unit_states "
                                   "WHERE version_id = :v AND unit_id >= 9000 ORDER BY unit_id"), {"v": v}).all()
            assert [tuple(r) for r in units] == [(9101, "M-1", 9001, None, "2"), (9102, "M-2", 9001, None, "")]
            cat = c.execute(text("SELECT code, title, kind, weight, escorted, sort_order FROM stays_category_states "
                                 "WHERE version_id = :v AND category_id = 9001"), {"v": v}).one()
            assert (cat[0], cat[1], cat[2], float(cat[3]), bool(cat[4]), cat[5]) == ("MIG", "Миграция", "villa", 4.0, True, 7)
            assert c.execute(text("SELECT unit_id FROM stays_assignments WHERE reservation_id = 9201")).scalar_one() == 9101
        command.downgrade(config(), "0009")
        with engine.connect() as c:
            rows = c.execute(text("SELECT id, label, category_id, floor, active FROM stays_units "
                                  "WHERE id >= 9100 ORDER BY id")).all()
            assert [(r[0], r[1], r[2], r[3], bool(r[4])) for r in rows] == [
                (9101, "M-1", 9001, "2", True), (9102, "M-2", 9001, "", True),
                (9103, "unit-9103", 9001, "", False)]     # неактивного в исходной версии не было: заглушка
            code, title, kind, weight, esc = c.execute(text(
                "SELECT code, title, kind, weight, escorted FROM stays_categories WHERE id = 9001")).one()
            assert (code, title, kind, float(weight), bool(esc)) == ("MIG", "Миграция", "villa", 4.0, True)
    finally:
        command.upgrade(config(), "head")
