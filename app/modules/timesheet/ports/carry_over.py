"""CarryOverPort (7.3): отложенные блоки без reason_code (v7/R1); save_deferred
ЗАМЕНЯЕТ вход следующего периода (7.2: исчезнувшие переносы удаляются)."""
from __future__ import annotations

from typing import Protocol, Sequence

from ..domain.types.entities import DeferredBlock, Period


class CarryOverPort(Protocol):
    def load_deferred(self, employee_id: str, period: Period) -> Sequence[DeferredBlock]: ...
    def save_deferred(self, employee_id: str, next_period: Period,
                      blocks: Sequence[DeferredBlock]) -> None: ...
