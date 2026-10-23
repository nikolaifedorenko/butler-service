"""DutyPort: смены и отсутствия батлеров на диапазон дат (§4.4, §5) — одним запросом,
против актуального Графика при каждом чтении; кэша, который мог бы устареть, нет."""
from __future__ import annotations

import datetime as dt
from typing import Mapping, Protocol, Sequence

from ..domain.types import OFF, DutyDay  # noqa: F401  (порт отдаёт доменный тип)


class DutyPort(Protocol):
    def duty(self, employee_ids: Sequence[int], first: dt.date,
             last: dt.date) -> Mapping[tuple[int, dt.date], DutyDay]: ...
