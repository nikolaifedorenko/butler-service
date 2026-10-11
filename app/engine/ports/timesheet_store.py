"""TimesheetStorePort (7.3, 16.5): запись строки Табеля. Валидация записи — теми же
доменными проверочными функциями в application (16.5, v7.1/F-16); вторые копии правил
на стороне записи запрещены."""
from __future__ import annotations

import datetime as dt
from typing import Protocol

from ..domain.types.entities import Minutes


class TimesheetStorePort(Protocol):
    def save_day(self, employee_id: str, day: dt.date, code: str,
                 plan_minutes: Minutes | None) -> None: ...
