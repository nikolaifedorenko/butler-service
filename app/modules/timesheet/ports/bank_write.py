"""BankWritePort (7.3): закрывающий банк периода."""
from __future__ import annotations

from typing import Protocol

from ..domain.types.entities import Minutes, Period


class BankWritePort(Protocol):
    def save_closing_bank(self, employee_id: str, period: Period,
                          closing_minutes: Minutes) -> None: ...
