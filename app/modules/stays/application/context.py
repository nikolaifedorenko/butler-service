"""Контекст покрытия на диапазон дат (§4.2–§4.4): кто где ночует, строки покрытия, График —
пакетно, одним набором запросов. Все виды и предпросмотр читают покрытие только отсюда;
предупреждения считаются при каждом чтении против актуального Графика."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.employees.application.catalog import Employee

from ..adapters.orm import (
    Assignment,
    Category,
    CoverageGuest,
    CoverageLine,
    Escort,
    Guest,
    Move,
    Occupant,
    Reservation,
    Unit,
)
from ..domain.coverage import resolve_day
from ..domain.halfday import PM, Segment, segment_on, segments
from ..domain.load import day_loads
from ..domain.types import DayCover, Line, StayDay, Warning
from ..domain.warnings import day_warnings
from ..ports.duty import DutyDay, DutyPort
from . import allocation
from .fund import get_settings
from .guests import short_name

NO_GUESTS = 0          # бронь без состава — один «неизвестный» гость, чтобы дыра была видна


def nights(a: dt.date, b: dt.date) -> list[dt.date]:
    return [a + dt.timedelta(days=i) for i in range((b - a).days)]


@dataclass
class StaysContext:
    first: dt.date
    last: dt.date
    vip_bonus: float
    vvip_bonus: float
    limit: float
    codes: frozenset[str]
    cats: dict[int, Category]
    units: dict[int, Unit]
    res: dict[int, Reservation]
    segs: dict[int, list[Segment]]
    asg: dict[tuple[int, int], int | None]
    occ: dict[int, list[Occupant]]
    guests: dict[int, Guest]
    lines: list[Line]
    escorts: list[int]
    staff: dict[int, str]
    duty: dict[tuple[int, dt.date], DutyDay]
    _memo: dict = field(default_factory=dict)

    def days(self) -> list[dt.date]:
        return nights(self.first, self.last + dt.timedelta(days=1))

    def unit_of(self, rid: int, day: dt.date) -> tuple[int | None, Segment | None]:
        seg = segment_on(self.segs[rid], day, PM)
        return (self.asg.get((rid, seg.index)) if seg else None), seg

    def stays_on(self, day: dt.date) -> list[StayDay]:
        key = ("stays", day)
        if key not in self._memo:
            self._memo[key] = self._stays_on(day)
        return self._memo[key]

    def _stays_on(self, day: dt.date) -> list[StayDay]:
        out = []
        for rid, r in self.res.items():
            if not r.check_in <= day < r.check_out:
                continue
            unit_id, seg = self.unit_of(rid, day)
            cat = self.cats[seg.category_id if seg else r.category_id]
            present = {o.guest_id: self.guests[o.guest_id].level for o in self.occ.get(rid, ())
                       if o.date_from <= day < o.date_to and o.guest_id in self.guests}
            if not self.occ.get(rid):
                present = {NO_GUESTS: "regular"}
            if not present:
                continue
            unit = self.units.get(unit_id)
            out.append(StayDay(day, rid, r.group_id, unit_id, unit.building if unit else "", float(cat.weight),
                               cat.escorted, r.declined_butler, present))
        return out

    def lines_on(self, day: dt.date) -> list[Line]:
        return [ln for ln in self.lines if ln.day == day]

    def cover(self, day: dt.date) -> DayCover:
        key = ("cover", day)
        if key not in self._memo:
            self._memo[key] = resolve_day(self.stays_on(day), self.lines_on(day))
        return self._memo[key]

    def loads(self, day: dt.date) -> dict[int, float]:
        key = ("loads", day)
        if key not in self._memo:
            self._memo[key] = day_loads(self.stays_on(day), self.cover(day), self.vip_bonus, self.vvip_bonus)
        return self._memo[key]

    def warnings(self, day: dt.date) -> list[Warning]:
        key = ("warnings", day)
        if key not in self._memo:
            self._memo[key] = day_warnings(day, self.stays_on(day), self.lines_on(day), self.cover(day),
                                           self.loads(day), self.duty, self.limit, self.codes)
        return self._memo[key]

    def name(self, employee_id: int | None) -> str:
        return self.staff.get(employee_id, "") if employee_id else ""

    def unit_label(self, unit_id: int | None) -> str:
        return self.units[unit_id].label if unit_id in self.units else "без объекта"

    def guest_name(self, guest_id: int) -> str:
        return short_name(self.guests[guest_id]) if guest_id in self.guests else "гость брони"

    def warning_text(self, w: Warning) -> str:
        who = self.name(w.employee_id)
        return {
            "hole": f"{self.unit_label(w.unit_id)}: гости без батлера",
            "double_cover": f"{self.unit_label(w.unit_id)}: гостя ведут два батлера",
            "need_replacement": f"{who}: {w.value} — нужна подмена",
            "off_shift": f"{who} вне смены — переработка",
            "overload": f"{who}: нагрузка {w.value}",
        }.get(w.kind, w.kind)


def _line_rows(db: Session, first: dt.date, last: dt.date) -> list[Line]:
    rows = list(db.scalars(select(CoverageLine).where(CoverageLine.day >= first, CoverageLine.day <= last)))
    picked: dict[int, set[int]] = {r.id: set() for r in rows}
    if rows:
        for cg in db.scalars(select(CoverageGuest).where(CoverageGuest.coverage_id.in_(list(picked)))):
            picked[cg.coverage_id].add(cg.guest_id)
    return [Line(r.id, r.day, r.employee_id, r.reservation_id, r.group_id, frozenset(picked[r.id]), r.source,
                 r.overnight) for r in rows]


def load_context(db: Session, first: dt.date, last: dt.date, duty: DutyPort | None) -> StaysContext:
    """Брони, ночующие в [first, last], их сегменты, объекты, гости, строки покрытия, список
    «Сопровождают гостей» и График (если передан duty) — пакетно."""
    st = get_settings(db)
    cats = {c.id: c for c in db.scalars(select(Category))}
    units = {u.id: u for u in db.scalars(select(Unit))}
    res = {r.id: r for r in db.scalars(select(Reservation).where(
        Reservation.status.in_(allocation.OCCUPYING), Reservation.check_in <= last, Reservation.check_out > first))}
    rids = list(res)
    moves: dict[int, list] = {rid: [] for rid in rids}
    asg: dict[tuple[int, int], int | None] = {}
    occ: dict[int, list[Occupant]] = {rid: [] for rid in rids}
    if rids:
        for m in db.scalars(select(Move).where(Move.reservation_id.in_(rids))):
            moves[m.reservation_id].append((m.move_date, m.category_id))
        for a in db.scalars(select(Assignment).where(Assignment.reservation_id.in_(rids))):
            asg[(a.reservation_id, a.seg_index)] = a.unit_id
        for o in db.scalars(select(Occupant).where(Occupant.reservation_id.in_(rids))):
            occ[o.reservation_id].append(o)
    gids = {o.guest_id for os in occ.values() for o in os}
    guests = {g.id: g for g in db.scalars(select(Guest).where(Guest.id.in_(gids)))} if gids else {}
    segs = {rid: segments(r.check_in, r.check_out, r.early, r.late, r.category_id, moves[rid])
            for rid, r in res.items()}
    lines = _line_rows(db, first, last)
    active_staff = dict(db.execute(select(Employee.id, Employee.full_name).where(Employee.active.is_(True))).all())
    escorts = [e.employee_id for e in db.scalars(select(Escort).where(Escort.active.is_(True)))
               if e.employee_id in active_staff]
    people = set(escorts) | {ln.employee_id for ln in lines}
    staff = {}
    if people:
        staff = {e.id: e.short_name or e.full_name for e in db.scalars(select(Employee).where(Employee.id.in_(people)))}
    got = dict(duty.duty(sorted(people), first, last)) if duty is not None and people else {}
    return StaysContext(first, last, float(st.vip_bonus), float(st.vvip_bonus), float(st.daily_limit),
                        frozenset(c for c in st.replacement_codes.split(",") if c), cats, units, res, segs, asg,
                        occ, guests, lines, escorts, staff, got)


def butlers_on(db: Session, day: dt.date, res: list[Reservation], moves: dict[int, list], asg: dict,
               occ: dict[int, list[Occupant]], guests: dict[int, Guest], cats: dict[int, Category],
               units: dict[int, Unit]) -> dict[int, list[str]]:
    """«Кто ведёт сегодня» из уже загруженных броней (шахматка объектов): строки покрытия дня
    и имена батлеров — два запроса вместо полного контекста (бюджет SQL, §10)."""
    lines = _line_rows(db, day, day)
    if not lines:
        return {}
    staff = {e.id: e.short_name or e.full_name for e in db.scalars(
        select(Employee).where(Employee.id.in_({ln.employee_id for ln in lines})))}
    live = {r.id: r for r in res if r.check_in <= day < r.check_out}
    ctx = StaysContext(day, day, 0.0, 0.0, 0.0, frozenset(), cats, units, live,
                       {rid: segments(r.check_in, r.check_out, r.early, r.late, r.category_id, moves.get(rid, []))
                        for rid, r in live.items()}, asg, occ, guests, lines, [], staff, {})
    out: dict[int, list[str]] = {}
    for (rid, _g), emps in ctx.cover(day).by_guest.items():
        for e in emps:
            if staff.get(e, "") not in out.setdefault(rid, []):
                out[rid].append(staff.get(e, ""))
    return out
