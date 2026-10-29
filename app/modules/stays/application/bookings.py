"""Вкладка «Брони» (спецификация фонда по версиям §8): плоский список бронирований с фильтрами §7
и сортировкой на сервере. Фильтры фонда — те же, что у шахматки (BoardFilters), и проверяются по
фонду каждого дня брони. Данные грузятся пакетами: число запросов не зависит от числа броней."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import Date, cast, literal, null, or_, select, union_all
from sqlalchemy.orm import Session

from app.modules.employees.application.catalog import Employee

from ..adapters.orm import Assignment, CoverageLine, Guest, Label, Move, Occupant, Reservation
from ..domain.allocate import natural_key
from ..domain.halfday import Piece, pieces, segments
from . import allocation
from .fund_versions import FundTimeline, boundary_pos, fund_day, fund_for_stays
from .guests import search_query, short_name
from .reservations import STATUS_TITLES
from .views import LEVEL_RANK, BoardFilters, ViewError, fund_match
from .visibility import LEVEL_ORDER, Level

Mode = Literal["stay", "check_in", "check_out", "created"]
MODES = ("stay", "check_in", "check_out", "created")
SORTS = ("number", "guest", "check_in", "check_out", "nights", "category", "unit", "status", "created_at")
MAX_LIMIT = 200
MAX_DAYS = 366


@dataclass(frozen=True)
class BookingQuery:
    first: dt.date
    last: dt.date
    mode: Mode = "stay"
    filters: BoardFilters = field(default_factory=BoardFilters)
    statuses: tuple[str, ...] = ()
    label_ids: tuple[int, ...] = ()
    unassigned: bool = False
    with_warnings: bool = False
    sort: str = "check_in"
    dir: Literal["asc", "desc"] = "asc"
    offset: int = 0
    limit: int = MAX_LIMIT

    def __post_init__(self) -> None:
        if self.last < self.first:
            raise ViewError("Конец периода раньше начала")
        if (self.last - self.first).days + 1 > MAX_DAYS:
            raise ViewError(f"Период списка броней — не больше {MAX_DAYS} дней")
        if self.mode not in MODES:
            raise ViewError("Неизвестный режим попадания в период")
        if self.sort not in SORTS:
            raise ViewError("Неизвестная колонка сортировки")
        if self.dir not in ("asc", "desc"):
            raise ViewError("Направление сортировки — asc или desc")
        if bad := [s for s in self.statuses if s not in STATUS_TITLES]:
            raise ViewError(f"Неизвестный статус: {', '.join(bad)}")
        if self.offset < 0 or not 1 <= self.limit <= MAX_LIMIT:
            raise ViewError(f"limit — от 1 до {MAX_LIMIT}, offset — не меньше 0")


@dataclass
class _Item:
    """Бронь с производными полями — для фильтров и сортировки."""
    r: Reservation
    label: Label | None
    occ: list[Occupant]
    pieces: list[Piece]
    units: list[tuple[int | None, str]]          # (объект, обозначение на дату части), подряд без повторов
    categories: list[str]
    butlers: list[str] = field(default_factory=list)
    butler_ids: set[int] = field(default_factory=set)
    main: str = ""
    top: str = "regular"


def _guest_text(g: Guest, can_guests: bool) -> str:
    """Текст поиска по гостю. Телефон — персональные данные уровня stays.guests: без права цифры
    телефона из текста убираются, иначе по ответу можно было бы подобрать номер."""
    text = g.search_text or ""
    digits = re.sub(r"\D", "", g.phone or "")
    return text if can_guests or not digits else text.replace(digits, "", 1)


def _candidates(db: Session, q: BookingQuery):
    stmt = select(Reservation, Label).outerjoin(Label, Label.id == Reservation.label_id)
    first, last = q.first, q.last
    if q.mode == "stay":
        stmt = stmt.where(Reservation.check_in <= last, Reservation.check_out >= first)
    elif q.mode == "check_in":
        stmt = stmt.where(Reservation.check_in >= first, Reservation.check_in <= last)
    elif q.mode == "check_out":
        stmt = stmt.where(Reservation.check_out >= first, Reservation.check_out <= last)
    else:
        one = dt.timedelta(days=1)
        stmt = stmt.where(Reservation.created_at >= dt.datetime.combine(first, dt.time()),
                          Reservation.created_at < dt.datetime.combine(last + one, dt.time()))
    if q.statuses:
        stmt = stmt.where(Reservation.status.in_(q.statuses))
    if q.label_ids:
        stmt = stmt.where(Reservation.label_id.in_(q.label_ids))
    return db.execute(stmt).all()


def _label_on(fund: FundTimeline, unit_id: int, day: dt.date) -> str:
    u = fund.unit(unit_id, day)
    return u.label if u is not None else ""


def _piece_passes(fund: FundTimeline, p: Piece, unit_id: int | None, day: dt.date, f: BoardFilters) -> bool:
    snap = fund.on(day)
    if not fund_match(snap, unit_id, p.category_id, f):
        return False
    if f.escorted_only:
        u = snap.units.get(unit_id) if unit_id is not None else None
        cat = snap.categories.get(u.category_id if u is not None else p.category_id)
        return bool(cat is not None and cat.escorted)
    return True


def find_bookings(db: Session, q: BookingQuery, level: Level, can_guests: bool) -> list[dict]:
    """Все брони, подходящие под запрос, в порядке сортировки (без среза страницы)."""
    if LEVEL_ORDER[level] < LEVEL_ORDER["names"]:
        raise PermissionError("Список броней без фамилий не показывается")
    f = q.filters.for_level(level)
    cand = _candidates(db, q)
    if not cand:
        return []
    rids = [r.id for r, _ in cand]
    # переезды и назначения — один запрос (UNION ALL): бюджет SQL вкладки — 12 запросов (§8, §10)
    moves: dict[int, list] = {rid: [] for rid in rids}
    asg: dict[tuple[int, int], int | None] = {}
    both = union_all(
        select(literal("m").label("kind"), Move.reservation_id.label("rid"), Move.category_id.label("a"),
               literal(0).label("b"), Move.move_date.label("d")).where(Move.reservation_id.in_(rids)),
        select(literal("a"), Assignment.reservation_id, Assignment.seg_index, Assignment.unit_id,
               cast(null(), Date)).where(Assignment.reservation_id.in_(rids)))
    for kind, rid, a, b, d in db.execute(both):
        if kind == "m":
            moves[rid].append((d, a))
        else:
            asg[(rid, a)] = b
    occ: dict[int, list[Occupant]] = {rid: [] for rid in rids}
    guests: dict[int, Guest] = {}
    for o, g in db.execute(select(Occupant, Guest).join(Guest, Guest.id == Occupant.guest_id)
                           .where(Occupant.reservation_id.in_(rids)).order_by(Occupant.date_from, Occupant.id)):
        occ[o.reservation_id].append(o)
        guests[g.id] = g
    fund = fund_for_stays(db, min(r.check_in for r, _ in cand), max(r.check_out for r, _ in cand))
    # окно фонда — с дня до самого раннего заезда по самый поздний выезд: его границы — все границы
    # версий внутри проживаний, части те же, что у распределения (version_cuts — лишний запрос бюджета)
    cuts = [boundary_pos(d) for d in fund.boundaries()]
    items: list[_Item] = []
    for r, lb in cand:
        ps = pieces(segments(r.check_in, r.check_out, r.early, r.late, r.category_id, moves[r.id]), cuts)
        live = r.status in allocation.OCCUPYING
        units: list[tuple[int | None, str]] = []
        cats: list[str] = []
        for p in ps:
            uid = asg.get((r.id, p.index)) if live else None
            day = fund_day(p.start_pos)
            if uid is not None and (not units or units[-1][0] != uid):
                units.append((uid, _label_on(fund, uid, day)))
            cat = fund.category(p.category_id, day) if fund.parts else None
            code = cat.code if cat is not None else "?"
            if not cats or cats[-1] != code:
                cats.append(code)
        it = _Item(r, lb, occ[r.id], ps, units, cats)
        it.top = max((guests[o.guest_id].level for o in it.occ if o.guest_id in guests),
                     key=lambda lv: LEVEL_RANK[lv], default="regular")
        mains = [o for o in it.occ if o.role == "main"]
        on_day = max(r.check_in, q.first) if q.mode == "stay" else r.check_in
        main = next((o for o in mains if o.date_from <= on_day < o.date_to), mains[0] if mains else None)
        it.main = short_name(guests[main.guest_id]) if main and main.guest_id in guests else ""
        items.append(it)

    # фильтры фонда: бронь проходит, если хотя бы одна её часть в окне проходит по фонду дня части
    has_fund_filter = bool(f.group_ids or f.category_ids or f.flag_ids or f.kind_ids or f.floor or f.escorted_only)
    if has_fund_filter or q.unassigned:
        win_a, win_b = (q.first, q.last) if q.mode == "stay" else (dt.date.min, dt.date.max)
        kept = []
        for it in items:
            in_win = [p for p in it.pieces if p.end >= win_a and p.start <= win_b] or it.pieces[:1]
            if q.unassigned and not (it.r.status in allocation.OCCUPYING
                                     and any(asg.get((it.r.id, p.index)) is None for p in in_win)):
                continue
            if has_fund_filter:
                if not fund.parts:
                    continue
                live = it.r.status in allocation.OCCUPYING
                if not any(_piece_passes(fund, p, asg.get((it.r.id, p.index)) if live else None,
                                         fund_day(p.start_pos), f) for p in in_win):
                    continue
            kept.append(it)
        items = kept

    if f.vip:
        items = [it for it in items if it.top != "regular"]
    if f.q.strip():
        needle = search_query(f.q)
        unit_text = {it.r.id: " ".join(lbl for _, lbl in it.units).lower() for it in items}
        items = [it for it in items if needle in (it.r.search_text or "") or needle in unit_text[it.r.id]
                 or any(needle in _guest_text(guests[o.guest_id], can_guests) for o in it.occ if o.guest_id in guests)]
    if q.with_warnings:
        state = allocation.current_state(db)
        flagged = {rid for w in state.warnings for rid in state.members[w.key]}
        items = [it for it in items if it.r.id in flagged]

    _attach_butlers(db, items)
    if f.employee_id:
        items = [it for it in items if f.employee_id in it.butler_ids]

    return [_row(it) for it in _sorted(items, q)]


def _attach_butlers(db: Session, items: list[_Item]) -> None:
    """Батлеры брони — по строкам покрытия на её ночи (на бронь или на её группу); один запрос."""
    if not items:
        return
    rids = [it.r.id for it in items]
    gids = {it.r.group_id for it in items if it.r.group_id is not None}
    cond = CoverageLine.reservation_id.in_(rids)
    if gids:
        cond = or_(cond, CoverageLine.group_id.in_(gids))
    by_res: dict[int, list[CoverageLine]] = {}
    by_group: dict[int, list[CoverageLine]] = {}
    names: dict[int, str] = {}
    for ln, short, full in db.execute(select(CoverageLine, Employee.short_name, Employee.full_name)
                                      .join(Employee, Employee.id == CoverageLine.employee_id).where(cond)
                                      .order_by(CoverageLine.day, CoverageLine.id)):
        names[ln.employee_id] = short or full
        if ln.reservation_id is not None:
            by_res.setdefault(ln.reservation_id, []).append(ln)
        else:
            by_group.setdefault(ln.group_id, []).append(ln)
    for it in items:
        r = it.r
        for ln in by_res.get(r.id, []) + (by_group.get(r.group_id, []) if r.group_id is not None else []):
            if r.check_in <= ln.day < r.check_out and ln.employee_id not in it.butler_ids:
                it.butler_ids.add(ln.employee_id)
                it.butlers.append(names[ln.employee_id])


def _sort_key(sort: str):
    return {
        "number": lambda it: natural_key(it.r.number),
        "guest": lambda it: it.main.lower(),
        "check_in": lambda it: it.r.check_in,
        "check_out": lambda it: it.r.check_out,
        "nights": lambda it: (it.r.check_out - it.r.check_in).days,
        "category": lambda it: it.categories[0].lower() if it.categories else "",
        "unit": lambda it: natural_key(it.units[0][1]) if it.units else ((2,),),
        "status": lambda it: it.r.status,
        "created_at": lambda it: it.r.created_at,
    }[sort]


def _sorted(items: list[_Item], q: BookingQuery) -> list[_Item]:
    """Вторичные ключи — номер, затем id — всегда по возрастанию (устойчивая сортировка)."""
    items = sorted(items, key=lambda it: (natural_key(it.r.number), it.r.id))
    return sorted(items, key=_sort_key(q.sort), reverse=q.dir == "desc")


def _row(it: _Item) -> dict:
    r = it.r
    return {"id": r.id, "number": r.number, "main_guest": it.main, "level": it.top,
            "check_in": r.check_in.isoformat(), "check_out": r.check_out.isoformat(),
            "nights": (r.check_out - r.check_in).days,
            "category": " → ".join(it.categories), "unit": " → ".join(lbl for _, lbl in it.units),
            "status": r.status, "status_title": STATUS_TITLES[r.status],
            "label": {"title": it.label.title, "color": it.label.color} if it.label else None,
            "butlers": it.butlers, "early": r.early, "late": r.late,
            "created_at": r.created_at.isoformat(timespec="minutes")}


def list_bookings(db: Session, q: BookingQuery, level: Level, can_guests: bool) -> dict:
    rows = find_bookings(db, q, level, can_guests)
    return {"total": len(rows), "rows": rows[q.offset:q.offset + q.limit]}
