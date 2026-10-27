"""Автораспределение по объектам поверх БД (§4.1, §9): читает фонд, блоки и занимающие
брони, вызывает domain.allocate и записывает stays_assignments. Запускается после каждой
операции, меняющей доступность: брони, статуса, блока, объекта.

Окно (ревью этапа 2, C1): в расчёт идут только брони с выездом не раньше сегодня; прошлые
не трогаются вовсе. Заселённые и выехавшие брони и сегменты, закончившиеся к сегодня,
заморожены: их объект — неявное закрепление. Так распределение не «переселяет» живущего
гостя и не переписывает историю, а время расчёта не растёт с накоплением броней."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import local_date

from ..adapters.orm import Assignment, Hold, Move, Reservation
from ..domain.allocate import AllocItem, AllocWarning, HoldRef, Key, UnitSpan, allocate
from ..domain.halfday import AM, PIECE_BASE, PM, hold_span, pieces, pos, segments
from .fund_versions import fund_on

# статусы, которые занимают объект (отменённая и no-show — нет, §4.7)
OCCUPYING = ("tentative", "confirmed", "in_house", "checked_out")
FROZEN_STATUSES = ("in_house", "checked_out")
CACHE_KEY = "stays_allocation"


@dataclass(frozen=True)
class AllocationState:
    units: dict[tuple[int, int], int | None]      # (reservation_id, seg_index) → unit_id
    pinned: dict[tuple[int, int], bool]
    warnings: list[AllocWarning]
    members: dict[Key, list[int]]                 # элемент распределения → брони


def _moves(db: Session, rids: list[int]) -> dict[int, list[tuple]]:
    out: dict[int, list[tuple]] = {rid: [] for rid in rids}
    if rids:
        for m in db.scalars(select(Move).where(Move.reservation_id.in_(rids))):
            out[m.reservation_id].append((m.move_date, m.category_id))
    return out


def compute(db: Session) -> AllocationState:
    """Распределение без записи: им пользуются и сохранение, и снимок предпросмотра."""
    today = local_date()
    # этап 1: распределение по фонду сегодняшнего дня; границы версий внутри окна — этап 2
    fund = fund_on(db, today)
    holds = [HoldRef(h.unit_id, *hold_span(h.start, h.end), h.title or ("OOO" if h.kind == "ooo" else "Блок"))
             for h in db.scalars(select(Hold).where(Hold.end >= today))]
    res = list(db.scalars(select(Reservation).where(Reservation.status.in_(OCCUPYING),
                                                    Reservation.check_out >= today)))
    # этап 2 (переходно, до задачи 2.3): один интервал на объект на всё окно, без границ версий
    lo = pos(min([today, *(r.check_in for r in res)]), AM)
    hi = pos(max([today, *(r.check_out for r in res)]), PM)
    spans = [UnitSpan(u.id, u.category_id, fund.categories[u.category_id].sort_order, u.label,
                      fund.unit_path(u.id), lo, hi)
             for u in fund.units.values()]
    moves = _moves(db, [r.id for r in res])
    pins: dict[tuple[int, int], int] = {}
    current: dict[tuple[int, int], int] = {}
    if res:
        for a in db.scalars(select(Assignment).where(Assignment.reservation_id.in_([r.id for r in res]))):
            if a.unit_id is not None:
                current[(a.reservation_id, a.seg_index)] = a.unit_id
                if a.pinned:
                    pins[(a.reservation_id, a.seg_index)] = a.unit_id

    frozen: dict[tuple[int, int], int] = {}          # (бронь, сегмент) → объект, без распределения

    def is_frozen(r: Reservation, seg) -> bool:
        return (r.status in FROZEN_STATUSES or seg.end <= today) and (r.id, seg.index) in current

    groups: dict[int, list[Reservation]] = {}
    items: list[AllocItem] = []
    members: dict[Key, list[int]] = {}

    def add_item(key: Key, number: str, rs: list[Reservation], segs) -> None:
        live = []
        for s in segs:
            fixed = next((current[(r.id, s.index)] for r in rs if is_frozen(r, s)), None)
            if fixed is None:
                live.append(s)
                continue
            # заморожен: объект не меняется ни при каком распределении, лишь занимает время
            for r in rs:
                frozen[(r.id, s.index)] = fixed
            holds.append(HoldRef(fixed, s.start_pos, s.end_pos, f"бронь {number}"))
        pinned = {s.index: uid for s in live
                  if (uid := next((pins[(r.id, s.index)] for r in rs if (r.id, s.index) in pins), None)) is not None}
        items.append(AllocItem(key, number, tuple(pieces(live, [])), pinned))
        members[key] = [r.id for r in rs]

    for r in res:
        if r.group_id is not None:
            groups.setdefault(r.group_id, []).append(r)
            continue
        add_item(("r", r.id), r.number or str(r.id), [r],
                 segments(r.check_in, r.check_out, r.early, r.late, r.category_id, moves[r.id]))
    for gid, rs in groups.items():
        # группа — один элемент с датами-оболочкой; переезды и категория у членов совпадают
        rs.sort(key=lambda r: r.id)
        first = min(rs, key=lambda r: (r.check_in, not r.early))
        last = max(rs, key=lambda r: (r.check_out, r.late))
        add_item(("g", gid), rs[0].number or f"группа {gid}", rs,
                 segments(first.check_in, last.check_out, first.early, last.late, rs[0].category_id,
                          moves[rs[0].id]))

    got, warnings = allocate(spans, holds, items, {c.id: c.code for c in fund.categories.values()})
    # без границ часть = сегмент: индекс части → seg_index (Assignment хранит сегменты до задачи 2.3)
    released = {(w.key, w.piece_index // PIECE_BASE) for w in warnings if w.kind == "pin_invalid"}
    out_units: dict[tuple[int, int], int | None] = {}
    out_pinned: dict[tuple[int, int], bool] = {}
    for (key, piece), uid in got.items():
        seg = piece // PIECE_BASE
        for rid in members[key]:
            out_units[(rid, seg)] = uid
            out_pinned[(rid, seg)] = (rid, seg) in pins and (key, seg) not in released
    for k, uid in frozen.items():
        out_units[k] = uid
        out_pinned[k] = k in pins
    return AllocationState(out_units, out_pinned, warnings, members)


def run_allocation(db: Session) -> AllocationState:
    """Пересчитать и записать назначения броней окна: строки неактуальных сегментов и
    незанимающих броней удаляются, закрепление снимается только у неподходящего объекта.
    Состояние кладётся в сессию — снимок «после» и ответ не считают его заново."""
    state = compute(db)
    in_window = select(Reservation.id).where(Reservation.check_out >= local_date())
    rows = {(a.reservation_id, a.seg_index): a
            for a in db.scalars(select(Assignment).where(Assignment.reservation_id.in_(in_window)))}
    for k, a in rows.items():
        if k not in state.units:
            db.delete(a)
    for (rid, seg), uid in state.units.items():
        a = rows.get((rid, seg))
        if a is None:
            a = Assignment(reservation_id=rid, seg_index=seg)
            db.add(a)
        a.unit_id = uid
        a.pinned = state.pinned[(rid, seg)]
    db.flush()
    db.info[CACHE_KEY] = state
    return state


def current_state(db: Session) -> AllocationState:
    """Состояние после последней записи в этой сессии, иначе — свежий расчёт."""
    return db.info.get(CACHE_KEY) or compute(db)


def warnings_for(state: AllocationState, rid: int) -> list[str]:
    keys = {k for k, rids in state.members.items() if rid in rids}
    return [w.text for w in state.warnings if w.key in keys]
