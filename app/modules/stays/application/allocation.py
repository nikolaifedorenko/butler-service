"""Автораспределение по объектам поверх БД (§4.1, §9): читает фонд, блоки и занимающие
брони, вызывает domain.allocate и записывает stays_assignments. Запускается после каждой
операции, меняющей доступность: брони, статуса, блока, объекта, публикации версии фонда.

Версии фонда (спецификация версий §5): объекты — интервалами по частям FundTimeline, сегменты
режутся на части в границах версий; Assignment.seg_index — индекс части
(seg_index * PIECE_BASE + n), закрепление хранится на частях, но действует на сегмент.

Окно (ревью этапа 2, C1): в расчёт идут только брони с выездом не раньше сегодня; прошлые
не трогаются вовсе. Заселённые и выехавшие брони и части, закончившиеся к сегодня, заморожены:
их объект — неявное закрепление. Часть, закончившаяся до сегодняшнего утра без объекта, тоже
заморожена — «без объекта» как исторический факт (находка L1 аудита). Так распределение не
«переселяет» живущего гостя и не переписывает историю, а время расчёта не растёт с
накоплением броней."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import local_date

from ..adapters.orm import Assignment, Hold, Move, Reservation
from ..domain.allocate import AllocItem, AllocWarning, HoldRef, Key, UnitSpan, allocate, pin_invalid
from ..domain.halfday import AM, PIECE_BASE, PM, Piece, hold_span, pieces, pos, segments
from .fund_versions import FundTimeline, boundary_pos, fund_for

# статусы, которые занимают объект (отменённая и no-show — нет, §4.7)
OCCUPYING = ("tentative", "confirmed", "in_house", "checked_out")
FROZEN_STATUSES = ("in_house", "checked_out")
CACHE_KEY = "stays_allocation"


@dataclass(frozen=True)
class AllocationState:
    units: dict[tuple[int, int], int | None]      # (reservation_id, индекс части) → unit_id
    pinned: dict[tuple[int, int], bool]
    warnings: list[AllocWarning]
    members: dict[Key, list[int]]                 # элемент распределения → брони; ("h", id) блока — []
    # (бронь, индекс части) → (start_pos, end_pos) части: индекс зависит от границ версий,
    # предпросмотр публикации сравнивает части «до/после» по покрытию, а не по индексу
    spans: dict[tuple[int, int], tuple[int, int]] = field(default_factory=dict)


def _moves(db: Session, rids: list[int]) -> dict[int, list[tuple]]:
    out: dict[int, list[tuple]] = {rid: [] for rid in rids}
    if rids:
        for m in db.scalars(select(Move).where(Move.reservation_id.in_(rids))):
            out[m.reservation_id].append((m.move_date, m.category_id))
    return out


def unit_spans(timeline: FundTimeline, lo: int, hi: int) -> list[UnitSpan]:
    """Интервалы объектов по частям фонда на [lo, hi]: часть версии с valid_from D начинается
    вечером D; соседние части с тем же состоянием объекта (категория, узел, обозначение)
    склеиваются, отсутствие в фонде разрывает интервал."""
    done: list[UnitSpan] = []
    open_: dict[int, UnitSpan] = {}
    parts = timeline.parts
    for i, (d, snap) in enumerate(parts):
        a = lo if i == 0 else boundary_pos(d)
        z = boundary_pos(parts[i + 1][0]) - 1 if i + 1 < len(parts) else hi
        here: dict[int, UnitSpan] = {}
        for u in snap.units.values():
            span = UnitSpan(u.id, u.category_id, snap.categories[u.category_id].sort_order, u.label,
                            snap.unit_path(u.id), a, z)
            prev = open_.pop(u.id, None)
            if prev is not None and replace(prev, start_pos=a, end_pos=z) == span:
                span = replace(prev, end_pos=z)
            elif prev is not None:
                done.append(prev)
            here[u.id] = span
        done += open_.values()                     # объекта нет в этой части фонда
        open_ = here
    return done + list(open_.values())


def _absent(spans: list[UnitSpan], unit_id: int, a: int, z: int) -> list[tuple[int, int]]:
    """Отрезки [a, z], где объекта нет в фонде (не покрыты его интервалами)."""
    out, p = [], a
    for s in sorted((s for s in spans if s.unit_id == unit_id), key=lambda s: s.start_pos):
        if s.end_pos < p or s.start_pos > z:
            continue
        if s.start_pos > p:
            out.append((p, s.start_pos - 1))
        p = max(p, s.end_pos + 1)
    if p <= z:
        out.append((p, z))
    return out


def _day(p: int) -> str:
    return dt.date.fromordinal(p // 2).strftime("%d.%m")


def effective_pin(pinned: dict[int, int], live: set[int]) -> int | None:
    """Объект закрепления сегмента по его закреплённым строкам (индекс части → объект): первой
    живой части (end_pos >= сегодня AM), иначе — первой прошлой. Прошлые строки не
    переписываются, поэтому новое закрепление видно по живым частям."""
    order = sorted(pinned)
    return next((pinned[i] for i in order if i in live), next((pinned[i] for i in order), None))


def compute(db: Session) -> AllocationState:
    """Распределение без записи: им пользуются и сохранение, и снимок предпросмотра."""
    today = local_date()
    hold_rows = list(db.scalars(select(Hold).where(Hold.end >= today)))
    res = list(db.scalars(select(Reservation).where(Reservation.status.in_(OCCUPYING),
                                                    Reservation.check_out >= today)))
    # фонд — с дня до самого раннего заезда: AM этого заезда принадлежит предыдущей версии
    first = min([today, *(r.check_in for r in res)]) - dt.timedelta(days=1)
    last = max([today, *(r.check_out for r in res), *(h.end for h in hold_rows)])
    timeline = fund_for(db, first, last)
    cuts = [boundary_pos(d) for d in timeline.boundaries()]
    spans = unit_spans(timeline, pos(first, AM), pos(last, PM))
    codes = {c.id: c.code for snap in timeline.snapshots() for c in snap.categories.values()}

    holds: list[HoldRef] = []
    warnings: list[AllocWarning] = []
    members: dict[Key, list[int]] = {}
    for h in hold_rows:
        title = h.title or ("OOO" if h.kind == "ooo" else "Блок")
        hs, he = hold_span(h.start, h.end)
        holds.append(HoldRef(h.unit_id, hs, he, title))
        # OOO/блок на дни, когда объекта нет в фонде (спецификация версий §14); прошлое — не тревога
        for a, z in _absent(spans, h.unit_id, max(hs, pos(today, AM)), he):
            u = timeline.unit(h.unit_id, dt.date.fromordinal(a // 2))
            label = u.label if u is not None else f"#{h.unit_id}"
            warnings.append(AllocWarning("hold_absent", ("h", h.id), 0,
                                         f"{title}: объекта {label} нет в фонде {_day(a)}–{_day(z)}"))
            members[("h", h.id)] = []

    moves = _moves(db, [r.id for r in res])
    current: dict[tuple[int, int], int] = {}
    pinned_rows: set[tuple[int, int]] = set()
    pin_rows: dict[tuple[int, int], dict[int, int]] = {}   # (бронь, сегмент) → {часть: объект}
    if res:
        for a in db.scalars(select(Assignment).where(Assignment.reservation_id.in_([r.id for r in res]))
                            .order_by(Assignment.seg_index)):
            if a.unit_id is not None:
                current[(a.reservation_id, a.seg_index)] = a.unit_id
                if a.pinned:
                    pinned_rows.add((a.reservation_id, a.seg_index))
                    pin_rows.setdefault((a.reservation_id, a.seg_index // PIECE_BASE), {})[a.seg_index] = a.unit_id
    morning, evening = pos(today, AM), pos(today, PM)

    by_unit: dict[int, list[UnitSpan]] = {}
    for u in spans:
        by_unit.setdefault(u.unit_id, []).append(u)

    def unit_cat(uid: int, p: Piece) -> int | None:
        """Категория объекта на всей части; None — объекта нет в фонде на части целиком."""
        return next((u.category_id for u in by_unit.get(uid, ()) if u.start_pos <= p.start_pos
                     and p.end_pos <= u.end_pos), None)

    def frozen_unit(rs: list[Reservation], p: Piece, prev: Piece | None) -> tuple[bool, int | None, int | None]:
        """(заморожена ли часть, её объект, объект, который ей больше не подходит).

        Закончившаяся до сегодняшнего утра — заморожена безусловно, и без объекта (L1).
        Заселённая/выехавшая или закончившаяся к сегодня — с текущим объектом. Часть, которая
        начинается с сегодняшнего вечера или позже (за границей версии — версия публикуется не
        раньше сегодня), заморожена, только пока объект есть в фонде на всей части и не сменил
        на границе категорию на чужую; иначе она распределяется заново, как незамороженная."""
        uid = next((current[(r.id, p.index)] for r in rs if (r.id, p.index) in current
                    and (r.status in FROZEN_STATUSES or p.end <= today)), None)
        if p.end_pos < morning:
            return True, uid, None
        if uid is None:
            return False, None, None
        if p.start_pos < evening:
            return True, uid, None          # фонд этой части уже действует — его не меняют
        cat = unit_cat(uid, p)
        before = unit_cat(uid, prev) if prev is not None and prev.seg_index == p.seg_index else cat
        if cat is not None and (cat == p.category_id or cat == before):
            return True, uid, None
        return False, None, uid

    groups: dict[int, list[Reservation]] = {}
    items: list[AllocItem] = []
    relocated: dict[tuple[Key, int], tuple[str, Piece, int]] = {}   # часть заселённой брони → прежний объект

    def add_item(key: Key, number: str, rs: list[Reservation], segs) -> None:
        ps = pieces(segs, cuts)
        live = {p.index for p in ps if p.end_pos >= morning}
        pinned = {s.index: uid for s in segs
                  if (uid := next((effective_pin(pin_rows[(r.id, s.index)], live) for r in rs
                                   if (r.id, s.index) in pin_rows), None)) is not None}
        fixed: dict[int, int | None] = {}
        settled = any(r.status in FROZEN_STATUSES for r in rs)
        for prev, p in zip((None, *ps), ps, strict=False):
            frozen, uid, lost = frozen_unit(rs, p, prev)
            pin = pinned.get(p.seg_index)
            if frozen:
                fixed[p.index] = uid
                if pin is not None and pin != uid and p.end_pos >= morning and unit_cat(pin, p) != p.category_id:
                    # часть уже отпущена с закрепления (pin_invalid): предупреждение остаётся
                    warnings.append(pin_invalid(number, key, p))
                continue
            if not settled or pin is not None:
                continue                  # у закреплённого сегмента о смене объекта скажет pin_invalid
            # заселённая бронь переезжает по фонду: объект строки или предыдущей части сегмента
            ref = lost if lost is not None else (
                fixed.get(prev.index) if prev is not None and prev.seg_index == p.seg_index else None)
            if ref is not None:
                relocated[(key, p.index)] = (number, p, ref)
        items.append(AllocItem(key, number, tuple(ps), pinned, fixed))
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
        first_r = min(rs, key=lambda r: (r.check_in, not r.early))
        last_r = max(rs, key=lambda r: (r.check_out, r.late))
        add_item(("g", gid), rs[0].number or f"группа {gid}", rs,
                 segments(first_r.check_in, last_r.check_out, first_r.early, last_r.late, rs[0].category_id,
                          moves[rs[0].id]))

    got, alloc_warnings = allocate(spans, holds, items, codes)
    warnings += alloc_warnings
    for (key, index), (number, p, ref) in relocated.items():
        if got.get((key, index)) != ref:
            u, new = timeline.unit(ref, p.start), got.get((key, index))
            nu = timeline.unit(new, p.start) if new is not None else None
            warnings.append(AllocWarning(
                "unit_invalid", key, index,
                f"Бронь {number}: объект {u.label if u else ref} не подходит по фонду с "
                f"{p.start.strftime('%d.%m')} — {'переезд в ' + nu.label if nu else 'без объекта'}"))
    released = {(w.key, w.piece_index) for w in alloc_warnings if w.kind == "pin_invalid"}
    fixed_keys = {(it.key, i) for it in items for i in it.fixed}
    out_units: dict[tuple[int, int], int | None] = {}
    out_pinned: dict[tuple[int, int], bool] = {}
    out_spans: dict[tuple[int, int], tuple[int, int]] = {}
    span_of = {(it.key, p.index): (p.start_pos, p.end_pos) for it in items for p in it.segments}
    for (key, piece), uid in got.items():
        for rid in members[key]:
            out_units[(rid, piece)] = uid
            if (key, piece) in span_of:
                out_spans[(rid, piece)] = span_of[(key, piece)]
            if (key, piece) in fixed_keys:
                out_pinned[(rid, piece)] = (rid, piece) in pinned_rows
            else:
                out_pinned[(rid, piece)] = ((rid, piece // PIECE_BASE) in pin_rows
                                            and (key, piece) not in released)
    return AllocationState(out_units, out_pinned, warnings, members, out_spans)


def run_allocation(db: Session) -> AllocationState:
    """Пересчитать и записать назначения броней окна: строки неактуальных частей и
    незанимающих броней удаляются, закрепление снимается только у неподходящего объекта.
    Состояние кладётся в сессию — снимок «после» и ответ не считают его заново."""
    state = compute(db)
    in_window = select(Reservation.id).where(Reservation.check_out >= local_date())
    rows = {(a.reservation_id, a.seg_index): a
            for a in db.scalars(select(Assignment).where(Assignment.reservation_id.in_(in_window)))}
    for k, a in rows.items():
        if k not in state.units:
            db.delete(a)
    for (rid, piece), uid in state.units.items():
        a = rows.get((rid, piece))
        if a is None:
            a = Assignment(reservation_id=rid, seg_index=piece)
            db.add(a)
        a.unit_id = uid
        a.pinned = state.pinned[(rid, piece)]
    db.flush()
    db.info[CACHE_KEY] = state
    return state


def current_state(db: Session) -> AllocationState:
    """Состояние после последней записи в этой сессии, иначе — свежий расчёт."""
    return db.info.get(CACHE_KEY) or compute(db)


def warnings_for(state: AllocationState, rid: int) -> list[str]:
    keys = {k for k, rids in state.members.items() if rid in rids}
    return [w.text for w in state.warnings if w.key in keys]
