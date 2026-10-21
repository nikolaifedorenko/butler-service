"""UnitOfWork (7.3): commit при успехе, rollback при исключении — всё или ничего."""
from __future__ import annotations

from typing import Protocol


class StorageConflictError(Exception):
    """Нарушение уникальности при сохранении (7.3, конкурентная запись).

    Контрактный сигнал порта: адаптер транслирует в него IntegrityError БД
    (например, `uq_closing_emp_period` при конкурентном закрытии периода),
    а use case придает конфликту бизнес-смысл (PeriodAlreadyClosedError — 409).
    Слой портов не знает ни sqlalchemy, ни домена (§3), слой application —
    ни драйвера БД, ни исключений инфраструктуры.
    """


class UnitOfWork(Protocol):
    def __enter__(self) -> UnitOfWork: ...
    def __exit__(self, *exc) -> None: ...
