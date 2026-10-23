"""Замок модуля на время записи (ревью этапа 2, I1): распределение по объектам пересчитывает
назначения всех будущих броней, поэтому две записи одновременно не должны читать одно и то
же состояние. PostgreSQL — транзакционный advisory-lock, SQLite — блокировка записи
(пустой UPDATE берёт RESERVED до первого чтения). Снимается с концом транзакции."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

LOCK_KEY = 0x53544159          # «STAY»


def lock_module(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK_KEY})
    else:
        db.execute(text("UPDATE stays_settings SET id = id WHERE id = 1"))
