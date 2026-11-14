"""OOO по половинам суток, блоки по категориям, пожелания гостей: схема, миграция, право, сброс, демо."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.modules.stays.adapters.orm import Block, BlockNight, Category, Guest, GuestPref, Ooo, Unit

D = dt.date(2040, 1, 10)


def _cat_unit(db):
    return db.scalar(select(Category.id).limit(1)), db.scalar(select(Unit.id).limit(1))


def test_tables_and_constraints(db):
    cat, unit = _cat_unit(db)
    blk = Block(title="Конференция", start=D, end=D + dt.timedelta(days=2))
    db.add(blk)
    db.flush()
    db.add(BlockNight(block_id=blk.id, category_id=cat, night=D, quantity=3))
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():       # PK ночи: одна строка на (блок, категория, ночь)
        db.add(BlockNight(block_id=blk.id, category_id=cat, night=D, quantity=1))
        db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():       # количество не меньше 1
        db.add(BlockNight(block_id=blk.id, category_id=cat, night=D + dt.timedelta(days=1), quantity=0))
        db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():       # половина суток — AM или PM
        db.add(Ooo(unit_id=unit, start=D, end=D, start_half="XX", end_half="PM"))
        db.flush()
    o = Ooo(unit_id=unit, start=D, end=D, start_half="PM", end_half="AM")
    g = Guest(last_name="Тестов", first_name="Т")
    db.add_all([o, g])
    db.flush()
    assert (o.version, o.reason) == (1, "") and o.created_at is not None
    with pytest.raises(IntegrityError), db.begin_nested():       # вид пожелания
        db.add(GuestPref(guest_id=g.id, kind="color", ref_id=1, priority=1))
        db.flush()
    db.add(GuestPref(guest_id=g.id, kind="flag", ref_id=1, priority=2))
    db.flush()
    db.rollback()


def test_overbook_perm_registered(db):
    from app.core.permissions import ALL_KEYS, role_permissions
    assert "stays.overbook" in ALL_KEYS
    for role in ("supervisor", "manager", "admin"):
        assert "stays.overbook" in role_permissions(db, role)
    assert "stays.overbook" not in role_permissions(db, "mgmt_view")


def test_reset_wipes_and_backs_up_new_tables(db):
    from app.modules.stays.application import fund_reset as fr
    cat, unit = _cat_unit(db)
    g = db.scalar(select(Guest).limit(1))
    blk = Block(title="Тест", start=D, end=D)
    db.add_all([blk, Ooo(unit_id=unit, start=D, end=D), GuestPref(guest_id=g.id, kind="unit", ref_id=unit)])
    db.flush()
    db.add(BlockNight(block_id=blk.id, category_id=cat, night=D, quantity=1))
    db.flush()
    names = fr.raw_sheet_names()
    for m in (Ooo, Block, BlockNight, GuestPref):
        assert m in fr.WIPE and m.__tablename__ in names
    assert {"ooo", "blocks"} <= set(fr.reset_counts(db))
    fr.wipe(db)
    for m in (Ooo, Block, BlockNight, GuestPref):
        assert db.scalar(select(func.count()).select_from(m)) == 0
    db.rollback()


def test_demo_has_ooo_and_blocks(fresh_database):
    """Демо на свежей базе (отдельный процесс: общую базу потока меняют другие тесты):
    2 OOO, в том числе с половинками, и 2 блока, один — с переменным остатком."""
    from tests.conftest import rows, run_migrate

    r = run_migrate(fresh_database, DEMO_SEED="1")
    assert r.returncode == 0, r.stderr[-2000:]
    ooo = rows(fresh_database, "SELECT start_half, end_half FROM stays_ooo")
    assert len(ooo) >= 2 and ("AM", "PM") in ooo and any(h != ("AM", "PM") for h in ooo)
    blocks = [b for (b,) in rows(fresh_database, "SELECT id FROM stays_blocks")]
    assert len(blocks) >= 2
    qty = [[q for (q,) in rows(fresh_database, f"SELECT quantity FROM stays_block_nights WHERE block_id = {b} ORDER BY night")]
           for b in blocks]
    assert all(qty) and any(len(set(q)) > 1 for q in qty) and any(len(set(q)) == 1 for q in qty)
