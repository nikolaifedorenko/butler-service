"""Замок модуля на время записи: распределение по объектам пересчитывает назначения всех
будущих броней, поэтому две записи одновременно не должны читать одно и то же состояние.
Транзакционный advisory-lock PostgreSQL: снимается с концом транзакции."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

LOCK_KEY = 0x53544159          # «STAY»


def lock_module(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": LOCK_KEY})
