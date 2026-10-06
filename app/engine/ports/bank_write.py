from typing import Protocol

from ..domain.types.entities import Period


class BankWritePort(Protocol):
    def save_closing_bank(self, employee_id: str, period: Period, closing_minutes: int) -> None: ...
