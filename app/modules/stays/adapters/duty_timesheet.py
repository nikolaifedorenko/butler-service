"""DutyPort поверх публичного запроса Графика (timesheet.application.roster)."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from sqlalchemy.orm import Session

from app.modules.timesheet.application.engine_common import engine_ports
from app.modules.timesheet.application.roster import roster

from ..ports.duty import DutyDay


class TimesheetDuty:
    def __init__(self, db: Session):
        self.db = db

    def duty(self, employee_ids: Sequence[int], first: dt.date, last: dt.date) -> dict[tuple[int, dt.date], DutyDay]:
        got = roster(list(employee_ids), first, last, engine_ports(self.db))
        return {k: DutyDay(v.on_shift, v.tabel_code, v.absence_minutes > 0) for k, v in got.items()}
