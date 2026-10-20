"""UnitOfWork (7.3): commit при успехе, rollback при исключении — всё или ничего."""
from __future__ import annotations

from typing import Protocol


class UnitOfWork(Protocol):
    def __enter__(self) -> UnitOfWork: ...
    def __exit__(self, *exc) -> None: ...
