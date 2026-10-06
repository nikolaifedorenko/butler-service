"""UnitOfWork поверх сессии SQLAlchemy: commit при успехе, rollback при исключении."""
from __future__ import annotations

from sqlalchemy.orm import Session


class SqlUnitOfWork:
    def __init__(self, db: Session):
        self.db = db

    def __enter__(self) -> "SqlUnitOfWork":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.db.commit()
        else:
            self.db.rollback()
