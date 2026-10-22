"""In-memory порты для application-тестов (13 п.15, 16): поведение — по контрактам
2.6/7.3/7.4, включая границы выборок [from, to), строго <, первая ≥, замену переносов,
снимок флагов, PeriodState (previous/next/opening_bank_set) и откат UnitOfWork."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from app.modules.timesheet.application.context import EnginePorts
from app.modules.timesheet.application.months import previous_period
from app.modules.timesheet.domain.settings.defaults import default_settings
from app.modules.timesheet.domain.settings.types import Settings
from app.modules.timesheet.domain.types.entities import (
    Adjustment,
    Day,
    Employment,
    Mark,
    Period,
    PeriodState,
    ShiftEntry,
)

UTC = dt.timezone.utc
TZ = dt.timezone.utc        # фолбэк; тесты задают tz настроек явно (Europe/Moscow)


def _clone(obj):
    """Структурный клон контейнеров: frozen-объекты домена копируются по ссылке
    (они неизменяемы), mappingproxy не pickle'уется — deepcopy неприменим."""
    if isinstance(obj, dict):
        return {k: _clone(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clone(v) for v in obj]
    return obj


@dataclass
class FakeDb:
    settings: Settings = field(default_factory=default_settings)
    settings_by_period: dict = field(default_factory=dict)
    timesheet_rows: list = field(default_factory=list)       # list[Day]
    marks: list = field(default_factory=list)                # list[Mark] (все сотрудники)
    shifts: list = field(default_factory=list)               # list[Shift]
    absences: list = field(default_factory=list)             # list[Absence]
    adjustments: list = field(default_factory=list)          # list[(emp, date, minutes, reason)]
    employment: dict = field(default_factory=dict)           # emp -> Employment
    active: list = field(default_factory=list)               # emp ids трудоустроенные сегодня
    closings: dict = field(default_factory=dict)             # (emp, start) -> dict
    deferred: dict = field(default_factory=dict)             # (emp, start) -> [DeferredBlock]
    manual_shifts: dict = field(default_factory=dict)        # (emp, day) -> [Shift]
    dropped_manual: list = field(default_factory=list)
    generated: dict = field(default_factory=dict)            # (emp, start, end) -> [ShiftEntry]
    saved_days: list = field(default_factory=list)           # (emp, day, code, plan)
    absences_store: list = field(default_factory=list)       # (id, emp, start, end)
    queries: list = field(default_factory=list)              # журнал батч-запросов
    timesheet_calls: list = field(default_factory=list)      # периоды вызовов days()
    punch_calls: list = field(default_factory=list)          # (метод, from, to/at)
    fail_on: str | None = None                               # инъекция сбоя записи
    _snapshot: dict | None = None

    def settings_for(self, period: Period) -> Settings:
        self.queries.append("settings.load")
        return self.settings_by_period.get((period.start, period.end), self.settings)

    # ── состояние для снапшотов/откатов ───────────────────────────────────────
    def _state(self) -> dict:
        return {"closings": _clone(self.closings),
                "deferred": _clone(self.deferred),
                "saved_days": list(self.saved_days),
                "manual_shifts": _clone(self.manual_shifts),
                "generated": _clone(self.generated),
                "timesheet_rows": list(self.timesheet_rows),
                "absences_store": list(self.absences_store)}

    def begin(self) -> None:
        self._snapshot = self._state()

    def rollback(self) -> None:
        if self._snapshot is not None:
            for key, value in self._snapshot.items():
                setattr(self, key, value)
            self._snapshot = None

    def commit(self) -> None:
        self._snapshot = None

    def op(self, name: str) -> None:
        if self.fail_on == name:
            raise RuntimeError(f"injected failure: {name}")


class FakeTimesheet:
    def __init__(self, db: FakeDb):
        self.db = db

    def days(self, employee_id: str, period: Period) -> list[Day]:
        self.db.queries.append("timesheet.days")
        self.db.timesheet_calls.append((employee_id, period))
        return [r for r in self.db.timesheet_rows
                if r.employee_id == employee_id and period.start <= r.day <= period.end]


class FakeTimesheetStore:
    def __init__(self, db: FakeDb):
        self.db = db

    def save_day(self, employee_id: str, day: dt.date, code: str, plan_minutes) -> None:
        self.db.op("save_day")
        self.db.saved_days.append((employee_id, day, code, plan_minutes))
        self.db.timesheet_rows = [r for r in self.db.timesheet_rows
                                  if not (r.employee_id == employee_id and r.day == day)]
        if code:
            self.db.timesheet_rows.append(Day(day, code, plan_minutes or 0, employee_id,
                                              "Смена 1"))


class FakePunch:
    def __init__(self, db: FakeDb):
        self.db = db

    def prefetch(self, employee_ids, from_utc, to_utc):
        pass

    def _emp(self, employee_id):
        return [m for m in self.db.marks if m.employee_id == employee_id]

    def marks_between(self, employee_id, from_utc, to_utc):
        self.db.queries.append("punch.marks_between")
        self.db.punch_calls.append(("between", from_utc, to_utc))
        return sorted((m for m in self._emp(employee_id) if from_utc <= m.at_utc < to_utc),
                      key=lambda m: m.at_utc)

    def last_mark_before(self, employee_id, at_utc):
        self.db.queries.append("punch.last_mark_before")
        self.db.punch_calls.append(("before", at_utc, None))
        before = [m for m in self._emp(employee_id) if m.at_utc < at_utc]
        return max(before, key=lambda m: m.at_utc) if before else None

    def first_mark_after(self, employee_id, at_utc):
        self.db.queries.append("punch.first_mark_after")
        self.db.punch_calls.append(("after", at_utc, None))
        after = [m for m in self._emp(employee_id) if m.at_utc >= at_utc]
        return min(after, key=lambda m: m.at_utc) if after else None

    def last_marks(self, at_utc):
        self.db.queries.append("punch.last_marks")
        latest: dict[str, Mark] = {}
        for m in sorted(self.db.marks, key=lambda m: m.at_utc):
            if m.at_utc <= at_utc:
                latest[m.employee_id] = m
        return list(latest.values())


class FakeShift:
    def __init__(self, db: FakeDb):
        self.db = db

    def shifts(self, employee_id, period):
        self.db.queries.append("shift.shifts")
        return [s for s in self.db.shifts if s.employee_id == employee_id]

    def shifts_on_day(self, day):
        self.db.queries.append("shift.shifts_on_day")
        return list(self.db.shifts)


class FakeAbsence:
    def __init__(self, db: FakeDb):
        self.db = db

    def absences(self, employee_id, period):
        self.db.queries.append("absence.absences")
        return [a for a in self.db.absences if a.employee_id == employee_id]

    def absences_on_day(self, day):
        self.db.queries.append("absence.absences_on_day")
        return list(self.db.absences)


class FakeBank:
    def __init__(self, db: FakeDb):
        self.db = db

    def opening(self, employee_id, period):
        self.db.queries.append("bank.opening")
        prev = previous_period(period, self.db.settings_for(period).period_granularity)
        row = self.db.closings.get((employee_id, prev.start))
        return row["result"].bank_closed_minutes if row else 0

    def adjustments(self, employee_id, period):
        """Контракт адаптера: только корректировки своего периода; Adjustment.period —
        период расчёта (CHK-OPENING, v7/R9)."""
        self.db.queries.append("bank.adjustments")
        return [Adjustment(minutes, period, reason or "manual")
                for emp, date, minutes, reason in self.db.adjustments
                if emp == employee_id and period.start <= date <= period.end]


class FakeBankWrite:
    def __init__(self, db: FakeDb):
        self.db = db

    def save_closing_bank(self, employee_id, period, closing_minutes):
        self.db.op("save_closing_bank")
        self.db.queries.append("bank_write.save_closing_bank")
        row = self.db.closings.get((employee_id, period.start))
        if row is not None:
            row["closing_bank"] = closing_minutes


class FakeEmployment:
    def __init__(self, db: FakeDb):
        self.db = db

    def prefetch(self, employee_ids):
        pass

    def employment(self, employee_id, period):
        self.db.queries.append("employment.employment")
        return self.db.employment.get(employee_id, Employment(dt.date(1900, 1, 1), None))

    def active_employees(self, on_day):
        self.db.queries.append("employment.active_employees")
        return list(self.db.active)


class FakeSettings:
    def __init__(self, db: FakeDb):
        self.db = db

    def load(self, period):
        return self.db.settings_for(period)


class FakeCarryOver:
    def __init__(self, db: FakeDb):
        self.db = db

    def load_deferred(self, employee_id, period):
        self.db.queries.append("carry_over.load_deferred")
        return list(self.db.deferred.get((employee_id, period.start), []))

    def save_deferred(self, employee_id, next_period_, blocks):
        self.db.op("save_deferred")
        self.db.queries.append("carry_over.save_deferred")
        self.db.deferred[(employee_id, next_period_.start)] = list(blocks)


class FakeStore:
    def __init__(self, db: FakeDb):
        self.db = db

    def _closed(self, emp, start):
        return (emp, start) in self.db.closings

    def lock_marks(self, employee_ids, period):
        return {e: (s.closed, s.next_closed)
                for e in employee_ids for s in [self.period_state(e, period)]}

    def period_state(self, employee_id, period):
        self.db.queries.append("store.period_state")
        granularity = self.db.settings_for(period).period_granularity
        rows = [row for (emp, _start), row in self.db.closings.items() if emp == employee_id]
        first = not any(row["period"].start < period.start for row in rows)
        seed = any(reason == "OPENING_SEED" and period.start <= date <= period.end
                   for date, reason in self._seed_dates(employee_id))
        prev_day = period.start - dt.timedelta(days=1)
        previous_closed = (self._closed(employee_id, previous_period(period, granularity).start)
                           or any(row["period"].end == prev_day for row in rows))
        next_closed = any(row["period"].start > period.end for row in rows)
        return PeriodState(closed=self._closed(employee_id, period.start),
                           previous_closed=previous_closed, next_closed=next_closed,
                           opening_bank_set=first and seed)

    def _seed_dates(self, employee_id):
        return [(date, reason) for emp, date, _m, reason in self.db.adjustments
                if emp == employee_id]

    def closing_inputs(self, employee_id, period):
        row = self.db.closings.get((employee_id, period.start))
        return row["inputs"] if row else None

    def save_result(self, employee_id, period, result, flags, inputs_snapshot,
                    settings_versions, step_minutes=60):
        self.db.op("save_result")
        self.db.queries.append("store.save_result")
        if (employee_id, period.start) in self.db.closings:
            existing = self.db.closings[(employee_id, period.start)]
            existing.update(result=result, flags=flags, versions=list(settings_versions),
                            step=step_minutes, revision=existing.get("revision", 1) + 1)
            return
        self.db.closings[(employee_id, period.start)] = {
            "period": period, "result": result, "flags": flags, "inputs": inputs_snapshot,
            "versions": list(settings_versions), "step": step_minutes, "revision": 1}

    def load_result(self, employee_id, period):
        self.db.queries.append("store.load_result")
        row = self.db.closings.get((employee_id, period.start))
        return (row["result"], row["flags"]) if row else None


class FakeScheduleStore:
    def __init__(self, db: FakeDb):
        self.db = db

    def load_entries(self, employee_id, period):
        self.db.queries.append("schedule_store.load_entries")
        out = []
        for (emp, _day), shifts in self.db.manual_shifts.items():
            if employee_id is None or emp == employee_id:
                out += [ShiftEntry(s, "manual") for s in shifts]
        for (emp, _start, _end), entries in self.db.generated.items():
            if employee_id is None or emp == employee_id:
                out += list(entries)
        return out

    def save_manual(self, employee_id, day, shifts):
        self.db.op("save_manual")
        self.db.manual_shifts[(employee_id, day)] = list(shifts)

    def drop_manual(self, employee_id, day):
        self.db.op("drop_manual")
        self.db.dropped_manual.append((employee_id, day))
        self.db.manual_shifts.pop((employee_id, day), None)

    def replace_generated(self, employee_id, period, entries):
        self.db.op("replace_generated")
        self.db.generated[(employee_id, period.start, period.end)] = list(entries)

    def save_absence(self, employee_id, day, start_hhmm, end_hhmm, end_next_day):
        self.db.op("save_absence")
        self.db.absences_store.append((len(self.db.absences_store) + 1, employee_id, day,
                                       start_hhmm, end_hhmm, end_next_day))
        return len(self.db.absences_store)

    def drop_absence(self, absence_id):
        self.db.absences_store = [a for a in self.db.absences_store if a[0] != absence_id]


class FakeUnitOfWork:
    def __init__(self, db: FakeDb):
        self.db = db

    def __enter__(self):
        self.db.begin()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.db.rollback()
            return
        self.db.commit()


def build_fakes(db: FakeDb | None = None) -> tuple[FakeDb, EnginePorts]:
    db = db or FakeDb()
    ports = EnginePorts(
        timesheet=FakeTimesheet(db), punch=FakePunch(db), shift=FakeShift(db),
        absence=FakeAbsence(db), bank=FakeBank(db), employment=FakeEmployment(db),
        settings=FakeSettings(db), carry_over=FakeCarryOver(db), store=FakeStore(db),
        bank_write=FakeBankWrite(db), schedule_store=FakeScheduleStore(db),
        timesheet_store=FakeTimesheetStore(db), unit_of_work=lambda: FakeUnitOfWork(db))
    return db, ports
