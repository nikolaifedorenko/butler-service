"""Пакетные адаптеры: все данные для группы сотрудников и диапазона — фиксированным числом
запросов (сетка Графика, УТ, «Кто на работе» не должны делать запросы на каждого сотрудника)."""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...employment import employed_on
from ...models import BankAdjustment, DeferredCarry, Employee, EmploymentPeriod, PeriodClosing, Punch, TabelDay
from ..application.context import EnginePorts
from ..domain.types.entities import Adjustment, Day, DeferredBlock, Mark, Period
from ..ports.settlement_store import ClosingInputs, PeriodState
from ._db import days_of, emp_pk, local_naive_to_utc, utc_to_local_naive
from .clock import SystemClock
from .sql_closings import SqlBankWrite, SqlCarryOver, SqlSettlementStore, _block
from .sql_punch import _mark, sanitize
from .sql_schedule import ScheduleCache, SqlScheduleAdapter
from .sql_settings import SqlSettingsAdapter
from .sql_timesheet import EMPTY_DAY_CODE, employee_group
from .sql_uow import SqlUnitOfWork


class BulkData:
    def __init__(self, db: Session, emp_ids: list[int], lo: dt.datetime, hi: dt.datetime,
                 first: dt.date, last: dt.date):
        self.emps = {e.id: e for e in db.scalars(select(Employee).where(Employee.id.in_(emp_ids)))}
        self.punches: dict[int, list[Punch]] = {}
        for p in db.scalars(select(Punch).where(Punch.employee_id.in_(emp_ids), Punch.ts >= utc_to_local_naive(lo),
                                                Punch.ts < utc_to_local_naive(hi)).order_by(Punch.ts, Punch.id)):
            self.punches.setdefault(p.employee_id, []).append(p)
        last_ts = select(Punch.employee_id, func.max(Punch.ts).label("ts")).where(
            Punch.employee_id.in_(emp_ids), Punch.ts < utc_to_local_naive(lo)).group_by(Punch.employee_id).subquery()
        self.before: dict[int, Punch] = {}
        for p in db.scalars(select(Punch).join(last_ts, (Punch.employee_id == last_ts.c.employee_id)
                                               & (Punch.ts == last_ts.c.ts)).order_by(Punch.id)):
            self.before[p.employee_id] = p
        self.lo = lo
        self.tabel = {(r.employee_id, r.date): r for r in db.scalars(select(TabelDay).where(
            TabelDay.employee_id.in_(emp_ids), TabelDay.date >= first, TabelDay.date <= last))}
        self.periods: dict[int, list] = {}
        for p in db.scalars(select(EmploymentPeriod).where(EmploymentPeriod.employee_id.in_(emp_ids))):
            self.periods.setdefault(p.employee_id, []).append(p)
        self.closings: dict[int, list[PeriodClosing]] = {}
        for c in db.scalars(select(PeriodClosing).where(PeriodClosing.employee_id.in_(emp_ids))
                            .order_by(PeriodClosing.period_start)):
            self.closings.setdefault(c.employee_id, []).append(c)
        self.adjust: dict[int, list[BankAdjustment]] = {}
        for a in db.scalars(select(BankAdjustment).where(BankAdjustment.employee_id.in_(emp_ids))
                            .order_by(BankAdjustment.id)):
            self.adjust.setdefault(a.employee_id, []).append(a)
        self.carry: dict[tuple, list[DeferredCarry]] = {}
        for r in db.scalars(select(DeferredCarry).where(DeferredCarry.employee_id.in_(emp_ids))
                            .order_by(DeferredCarry.id)):
            self.carry.setdefault((r.employee_id, r.period_start), []).append(r)


class BulkPunch:
    def __init__(self, data: BulkData, now: dt.datetime):
        self.d, self.now = data, now

    def marks_between(self, employee_id, from_utc, to_utc):
        hi = min(to_utc, self.now + dt.timedelta(microseconds=1))
        ps = [p for p in self.d.punches.get(emp_pk(employee_id), [])
              if from_utc <= local_naive_to_utc(p.ts) < hi]
        return sanitize([_mark(p) for p in ps], self.last_mark_before(employee_id, from_utc))

    def last_mark_before(self, employee_id, at_utc) -> Mark | None:
        ps = [p for p in self.d.punches.get(emp_pk(employee_id), []) if local_naive_to_utc(p.ts) < at_utc]
        if ps:
            return _mark(ps[-1])
        p = self.d.before.get(emp_pk(employee_id))
        return _mark(p) if p and local_naive_to_utc(p.ts) < at_utc else None


class BulkTimesheet:
    def __init__(self, data: BulkData, settings):
        self.d, self.settings = data, settings

    def days(self, employee_id, period: Period) -> list[Day]:
        emp = self.d.emps.get(emp_pk(employee_id))
        if emp is None:
            return []
        group = employee_group(emp, set(self.settings.load(period).groups))
        periods = self.d.periods.get(emp.id, [])
        out = []
        for day in days_of(period.start, period.end):
            if periods and not employed_on(periods, day):
                continue
            r = self.d.tabel.get((emp.id, day))
            out.append(Day(day, r.code if r else EMPTY_DAY_CODE, r.plan_minutes if r else 0, employee_id, group))
        return out


class BulkBank:
    def __init__(self, data: BulkData):
        self.d = data

    def _adj(self, emp, lo, hi):
        return sum(int(round(a.hours * 60)) for a in self.d.adjust.get(emp, [])
                   if a.effective_date < hi and (lo is None or a.effective_date > lo))

    def opening(self, employee_id, period: Period) -> int:
        emp = emp_pk(employee_id)
        prev = [c for c in self.d.closings.get(emp, []) if c.period_end < period.start]
        if prev:
            return prev[-1].closing_bank_minutes + self._adj(emp, prev[-1].period_end, period.start)
        e = self.d.emps.get(emp)
        return int(round((e.balance_hours if e else 0.0) * 60)) + self._adj(emp, None, period.start)

    def adjustments(self, employee_id, period: Period):
        return [Adjustment(int(round(a.hours * 60)), "manual", a.note or None)
                for a in self.d.adjust.get(emp_pk(employee_id), []) if period.start <= a.effective_date <= period.end]


class BulkStore(SqlSettlementStore):
    """Чтение — из предзагрузки; запись — как у SqlSettlementStore."""

    def __init__(self, db: Session, data: BulkData, actor: str = ""):
        super().__init__(db, actor)
        self.d = data

    def _rows(self, employee_id):
        return self.d.closings.get(emp_pk(employee_id), [])

    def period_state(self, employee_id, period):
        rows = self._rows(employee_id)
        return PeriodState(any(r.period_start == period.start for r in rows),
                           any(r.period_start > period.end for r in rows))

    def closing_inputs(self, employee_id, period):
        row = next((r for r in self._rows(employee_id) if r.period_start == period.start), None)
        if row is None:
            return None
        return ClosingInputs(row.bank_open_minutes, tuple(_block(x) for x in json.loads(row.deferred_in_json or "[]")),
                             row.previous_step_minutes)

    def previous_step(self, employee_id, period):
        prev = [r for r in self._rows(employee_id) if r.period_end < period.start]
        return prev[-1].step_minutes if prev else None

    def load_result(self, employee_id, period):
        row = next((r for r in self._rows(employee_id) if r.period_start == period.start), None)
        return None if row is None else {"result": json.loads(row.result_json), "revision": row.revision,
                                         "closed_by": row.closed_by_name, "closed_at": row.closed_at.isoformat(),
                                         "versions": row.settings_versions.split(",")}


class BulkCarry(SqlCarryOver):
    def __init__(self, db: Session, data: BulkData):
        super().__init__(db)
        self.d = data

    def load_deferred(self, employee_id, period):
        return [DeferredBlock(r.source_day, r.tariff, r.minutes, r.reason_code)
                for r in self.d.carry.get((emp_pk(employee_id), period.start), [])]


def build_bulk_ports(db: Session, emp_ids: list[int], first: dt.date, last: dt.date, actor_name: str = "",
                     clock=None, margin_minutes: int = 60) -> EnginePorts:
    """Порты для чтения (view / preview) группы сотрудников за диапазон дат [first, last]."""
    from ._db import TZ
    clock = clock or SystemClock()
    margin = dt.timedelta(minutes=margin_minutes)
    lo = dt.datetime.combine(first - dt.timedelta(days=1), dt.time(0), TZ).astimezone(dt.timezone.utc) - margin
    hi = dt.datetime.combine(last + dt.timedelta(days=1), dt.time(0), TZ).astimezone(dt.timezone.utc) + margin
    data = BulkData(db, emp_ids, lo, hi, first, last)
    cache = ScheduleCache(db)
    cache.preload(emp_ids, first - dt.timedelta(days=1), last)
    settings = SqlSettingsAdapter(db)
    schedule = SqlScheduleAdapter(db, cache)
    schedule.db_get = data.emps.get
    return EnginePorts(timesheet=BulkTimesheet(data, settings), punch=BulkPunch(data, clock.now()),
                       shift=schedule, absence=schedule, bank=BulkBank(data), settings=settings,
                       carry_over=BulkCarry(db, data), store=BulkStore(db, data, actor_name),
                       bank_write=SqlBankWrite(db), unit_of_work=lambda: SqlUnitOfWork(db), clock=clock)
