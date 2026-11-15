"""Время ядра (ADR-0013, раздел 2): момент — только с поясом, в базе UTC; местное время —
в поясе объекта; строки API — местные, без смещения."""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.exc import StatementError

from app.core import time as t


def test_now_is_aware_utc():
    n = t.now()
    assert n.tzinfo is not None and n.utcoffset() == dt.timedelta(0)


def test_local_now_and_date_are_in_object_zone(freeze):
    with freeze("2026-11-12 21:30:00"):                    # 00:30 13.11 по Москве, 12.11 по UTC
        assert t.local_now().utcoffset() == dt.timedelta(hours=3)
        assert t.local_date() == dt.date(2026, 11, 13)
        assert t.now().date() == dt.date(2026, 11, 12)


def test_to_local_and_back():
    moment = dt.datetime(2026, 11, 12, 21, 30, tzinfo=dt.UTC)
    local = t.to_local(moment)
    assert local == moment and (local.hour, local.day) == (0, 13)
    assert t.to_local(None) is None
    assert t.from_local(dt.datetime(2026, 11, 13, 0, 30)) == moment


def test_from_local_rejects_aware_value():
    with pytest.raises(ValueError):
        t.from_local(dt.datetime(2026, 11, 13, 0, 30, tzinfo=dt.UTC))


def test_local_midnight_is_start_of_object_day():
    assert t.local_midnight(dt.date(2026, 11, 13)) == dt.datetime(2026, 11, 12, 21, 0, tzinfo=dt.UTC)


@pytest.mark.parametrize("timespec, expected", [
    ("seconds", "2026-11-13T00:30:05"), ("minutes", "2026-11-13T00:30"), ("auto", "2026-11-13T00:30:05")])
def test_local_iso_is_local_without_offset(timespec, expected):
    assert t.local_iso(dt.datetime(2026, 11, 12, 21, 30, 5, tzinfo=dt.UTC), timespec) == expected
    assert t.local_iso(None) is None


def test_utc_iso_is_utc_without_offset():
    moment = dt.datetime(2026, 11, 13, 0, 30, tzinfo=t.TZ)
    assert t.utc_iso(moment, "minutes") == "2026-11-12T21:30"
    assert t.utc_iso(None) is None


def test_moment_column_rejects_naive_and_returns_utc(db):
    from app.core.audit import AuditLog

    row = AuditLog(actor_name="t", action="core_time_probe", target="x", payload={},
                   ts=dt.datetime(2026, 11, 13, 0, 30, tzinfo=t.TZ))
    db.add(row)
    db.commit()
    try:
        db.expire_all()
        got = db.scalar(select(AuditLog).where(AuditLog.id == row.id))
        assert got.ts == dt.datetime(2026, 11, 12, 21, 30, tzinfo=dt.UTC)
        assert got.ts.utcoffset() == dt.timedelta(0)
        # сравнение в запросе — тоже только с поясом
        assert db.scalar(select(AuditLog.id).where(AuditLog.id == row.id,
                                                   AuditLog.ts < t.local_midnight(dt.date(2026, 11, 14)))) == row.id
        with pytest.raises(StatementError, match="без часового пояса"):
            db.scalar(select(AuditLog.id).where(AuditLog.ts < dt.datetime(2026, 11, 14)))
        db.rollback()
        got.ts = dt.datetime(2026, 11, 13, 0, 30)
        with pytest.raises(StatementError, match="без часового пояса"):
            db.commit()
        db.rollback()
    finally:
        db.delete(db.get(AuditLog, row.id))
        db.commit()


def test_schema_stores_every_moment_with_time_zone(db):
    """В базе нет времени без пояса: все колонки даты-времени — timestamptz."""
    from sqlalchemy import text

    types = dict(db.execute(text(
        "SELECT table_name || '.' || column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' AND data_type LIKE 'timestamp%'")).all())
    assert len(types) >= 60
    naive = sorted(c for c, kind in types.items() if kind != "timestamp with time zone")
    assert naive == []
