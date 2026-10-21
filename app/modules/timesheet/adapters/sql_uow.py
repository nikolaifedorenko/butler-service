"""UnitOfWork поверх сессии SQLAlchemy (7.3): commit при успехе, rollback при исключении."""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ports.unit_of_work import StorageConflictError


class SqlUnitOfWork:
    def __init__(self, db: Session):
        self.db = db

    def __enter__(self) -> SqlUnitOfWork:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.db.rollback()
            return
        try:
            self.db.commit()
        except IntegrityError as conflict:
            # страховка отложенного flush: конкурентная запись нарушила уникальность —
            # откат и контрактный сигнал порта (use case решает бизнес-смысл, P1-ts-1)
            self.db.rollback()
            raise StorageConflictError(str(getattr(conflict, "orig", conflict))) from conflict
