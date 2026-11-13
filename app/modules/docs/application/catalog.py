"""Публичная поверхность данных модуля docs (граница R3/R4)."""
from sqlalchemy import select

from ..adapters.orm import StatementKind  # noqa: F401


def statement_kind_exists(db, code: str) -> bool:
    return db.scalar(select(StatementKind.id).where(StatementKind.code == code)) is not None
