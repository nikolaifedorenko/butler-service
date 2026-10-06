"""Набор портов, с которыми работают use case'ы."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..ports.absence import AbsencePort
from ..ports.bank import BankPort
from ..ports.bank_write import BankWritePort
from ..ports.carry_over import CarryOverPort
from ..ports.clock import ClockPort
from ..ports.punch import PunchPort
from ..ports.settings import SettingsPort
from ..ports.settlement_store import SettlementStorePort
from ..ports.shift import ShiftPort
from ..ports.timesheet import TimesheetPort
from ..ports.unit_of_work import UnitOfWork


@dataclass(frozen=True)
class EnginePorts:
    timesheet: TimesheetPort
    punch: PunchPort
    shift: ShiftPort
    absence: AbsencePort
    bank: BankPort
    settings: SettingsPort
    carry_over: CarryOverPort
    store: SettlementStorePort
    bank_write: BankWritePort
    unit_of_work: Callable[[], UnitOfWork]
    clock: ClockPort
