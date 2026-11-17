"""Кто в какой день на смене: ``DutyPort`` поверх Графика для тех, кто читает шахматку."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..adapters.duty_timesheet import TimesheetDuty
from ..ports.duty import DutyPort


def timesheet_duty(db: Session) -> DutyPort:
    return TimesheetDuty(db)
