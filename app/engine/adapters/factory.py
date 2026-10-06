"""Сборка EnginePorts поверх сессии БД прототипа."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..application.context import EnginePorts
from .clock import SystemClock
from .sql_bank import SqlBankAdapter
from .sql_closings import SqlBankWrite, SqlCarryOver, SqlSettlementStore
from .sql_punch import SqlPunchAdapter
from .sql_schedule import ScheduleCache, SqlScheduleAdapter
from .sql_settings import SqlSettingsAdapter
from .sql_timesheet import SqlTimesheetAdapter
from .sql_uow import SqlUnitOfWork


def build_ports(db: Session, actor_name: str = "", clock=None, cache: ScheduleCache | None = None) -> EnginePorts:
    clock = clock or SystemClock()
    settings = SqlSettingsAdapter(db)
    schedule = SqlScheduleAdapter(db, cache)
    return EnginePorts(timesheet=SqlTimesheetAdapter(db, settings), punch=SqlPunchAdapter(db, clock.now()),
                       shift=schedule, absence=schedule, bank=SqlBankAdapter(db), settings=settings,
                       carry_over=SqlCarryOver(db), store=SqlSettlementStore(db, actor_name),
                       bank_write=SqlBankWrite(db), unit_of_work=lambda: SqlUnitOfWork(db), clock=clock)
