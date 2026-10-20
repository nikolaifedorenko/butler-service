"""Сборка EnginePorts поверх сессии БД прототипа (8.4). now передаёт composition root
(v7.1/F-15); ClockPort не вводится."""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from ..application.context import EnginePorts
from ._db import TZ
from .sql_bank import SqlBankAdapter
from .sql_closings import SqlBankWrite, SqlCarryOver, SqlSettlementStore
from .sql_employment import SqlEmploymentAdapter
from .sql_punch import SqlPunchAdapter
from .sql_schedule import SqlAbsenceAdapter, SqlScheduleStore, SqlShiftAdapter
from .sql_settings import SqlSettingsAdapter
from .sql_timesheet import SqlTimesheetAdapter
from .sql_timesheet_store import SqlTimesheetStore
from .sql_uow import SqlUnitOfWork


def build_ports(db: Session, now: dt.datetime, actor_name: str = "") -> EnginePorts:
    settings = SqlSettingsAdapter(db)
    return EnginePorts(
        timesheet=SqlTimesheetAdapter(db),
        punch=SqlPunchAdapter(db, now),
        shift=SqlShiftAdapter(db, TZ),
        absence=SqlAbsenceAdapter(db, TZ),
        bank=SqlBankAdapter(db, settings),
        employment=SqlEmploymentAdapter(db),
        settings=settings,
        carry_over=SqlCarryOver(db),
        store=SqlSettlementStore(db, settings, actor_name),
        bank_write=SqlBankWrite(db),
        schedule_store=SqlScheduleStore(db, TZ),
        timesheet_store=SqlTimesheetStore(db),
        unit_of_work=lambda: SqlUnitOfWork(db))
