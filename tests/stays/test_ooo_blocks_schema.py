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


_MIGRATE = """
import sqlite3, sys
from alembic import command
from app.bootstrap.schema_version import config
db = sys.argv[1]
def tables():
    con = sqlite3.connect(db)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        con.close()
NEW = {"stays_ooo", "stays_blocks", "stays_block_nights", "stays_guest_prefs"}
command.upgrade(config(), "0015")
up = tables()
assert NEW <= up and "stays_holds" not in up, up
command.downgrade(config(), "0014")
down = tables()
assert "stays_holds" in down and not NEW & down, down
command.upgrade(config(), "head")
assert NEW <= tables()
"""


def test_migration_up_down_sqlite(tmp_path):
    """0015 вверх и вниз на пустой SQLite отдельным процессом (общая тестовая база не трогается)."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'm.db'}", "DEMO_SEED": "0",
           "NIGHT_SYNC_ENABLED": "0"}
    r = subprocess.run([sys.executable, "-c", _MIGRATE, str(tmp_path / "m.db")], env=env,
                       cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=240)
    assert r.returncode == 0, r.stderr[-2000:]


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


def test_demo_has_ooo_and_blocks(tmp_path):
    """Демо на свежей базе (отдельный процесс: общая тестовая база теряет эти таблицы при откатах миграций
    в других тестах): 2 OOO, в том числе с половинками, и 2 блока, один — с переменным остатком."""
    import os
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path

    db = tmp_path / "demo.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "DEMO_SEED": "1", "NIGHT_SYNC_ENABLED": "0"}
    r = subprocess.run([sys.executable, "-m", "app.bootstrap.migrate"], env=env,
                       cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    con = sqlite3.connect(db)
    try:
        ooo = con.execute("SELECT start_half, end_half FROM stays_ooo").fetchall()
        assert len(ooo) >= 2 and ("AM", "PM") in ooo and any(h != ("AM", "PM") for h in ooo)
        blocks = [b for (b,) in con.execute("SELECT id FROM stays_blocks")]
        assert len(blocks) >= 2
        qty = [[q for (q,) in con.execute("SELECT quantity FROM stays_block_nights WHERE block_id = ? ORDER BY night", (b,))]
               for b in blocks]
        assert all(qty) and any(len(set(q)) > 1 for q in qty) and any(len(set(q)) == 1 for q in qty)
    finally:
        con.close()
