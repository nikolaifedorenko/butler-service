"""Автораспределение по объектам поверх БД (§4.1, §9): читает фонд, блоки и занимающие
брони, вызывает domain.allocate и записывает stays_assignments. Запускается после каждой
операции, меняющей доступность: брони, статуса, блока, объекта, публикации версии фонда.

Версии фонда (спецификация версий §5): объекты — интервалами по частям FundTimeline, сегменты
режутся на части в границах версий; Assignment.seg_index — индекс части
(seg_index * PIECE_BASE + n), закрепление хранится на частях, но действует на сегмент.
Переезд заселённого из-за OOO с ночи D режет часть ещё и в D: такие разрезы хранятся в
Assignment.start_pos (пишется у каждой строки), читатели режут сегменты по границам версий и
по ним (own_cuts). Закреплённая часть, оставшаяся без объекта, хранит объект закрепления в
Assignment.pin_unit_id (§4.4).

Окно (ревью этапа 2, C1): в расчёт идут только брони с выездом не раньше сегодня; прошлые
не трогаются вовсе. Части до сегодняшнего вечера у заселённых и выехавших и части,
закончившиеся к сегодня, заморожены: их объект — неявное закрепление. Часть, закончившаяся
до сегодняшнего утра без объекта, тоже заморожена — «без объекта» как исторический факт
(находка L1 аудита). Будущее заселённой брони держит объект, пока его не отнимут OOO или фонд
(часть 2 §4.3): тогда один переезд до выезда, раньше слотов блоков. Части 2: слоты блоков и
OOO — в расчёте, назначения слотов — только в AllocationState (без таблицы)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import local_date

from ..adapters.orm import Assignment, Block, BlockNight, Move, Ooo, Reservation
from ..domain.allocate import AllocItem, AllocWarning, Key, OooRef, SlotKey, UnitSpan, allocate
from ..domain.blocks import slots
from ..domain.halfday import AM, PIECE_BASE, PM, Piece, Segment, ooo_span, overlaps, pieces, pos, segments
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
    members: dict[Key, list[int]]                 # элемент распределения → брони; ("h"|"b", id) — []
    # (бронь, индекс части) → (start_pos, end_pos) части: индекс зависит от границ версий,
    # предпросмотр публикации сравнивает части «до/после» по покрытию, а не по индексу
    spans: dict[tuple[int, int], tuple[int, int]] = field(default_factory=dict)
    slots: dict[SlotKey, int | None] = field(default_factory=dict)   # (блок, категория, слот, ночь) → объект
    overbooked: frozenset[tuple[int, int]] = frozenset()            # (бронь, ordinal ночи) без объекта
    # закреплённая часть без объекта → объект закрепления (сохраняется до свободного объекта, §4.4)
    pin_units: dict[tuple[int, int], int] = field(default_factory=dict)


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


def absent_parts(spans: list[UnitSpan], unit_id: int, a: int, z: int) -> list[tuple[int, int]]:
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


def day_label(p: int) -> str:
    return dt.date.fromordinal(p // 2).strftime("%d.%m")


def pin_target(a: Assignment) -> int | None:
    """Объект закрепления строки: её объект, а у закреплённой части без объекта (овербукинг под
    OOO, §4.4) — сохранённый pin_unit_id; не закреплена — None."""
    if not a.pinned:
        return None
    return a.unit_id if a.unit_id is not None else a.pin_unit_id


def effective_pin(pinned: dict[int, int], live: set[int]) -> int | None:
    """Объект закрепления сегмента по его закреплённым строкам (индекс части → объект): последней
    живой части (end_pos >= сегодня AM), иначе — последней прошлой. Прошлые строки не
    переписываются, поэтому новое закрепление видно по живым частям; закрепление, перенесённое
    при переезде заселённого (OOO с ночи D), — по частям с D."""
    order = sorted(pinned, reverse=True)
    return next((pinned[i] for i in order if i in live), next((pinned[i] for i in order), None))


def _envelope(rs: list[Reservation], moves: dict[int, list[tuple]]) -> list[Segment]:
    """Сегменты группы — по датам-оболочке её членов; переезды и категория у членов совпадают."""
    rs.sort(key=lambda r: r.id)
    first_r = min(rs, key=lambda r: (r.check_in, not r.early))
    last_r = max(rs, key=lambda r: (r.check_out, r.late))
    return segments(first_r.check_in, last_r.check_out, first_r.early, last_r.late, rs[0].category_id,
                    moves[rs[0].id])


def own_cuts(cuts: list[int], starts: dict[int, list[int]], rid: int) -> list[int]:
    """Границы частей брони: границы версий фонда и начала её строк назначений — так виден
    переезд заселённого гостя посреди части фонда (OOO с ночи D, ревизия 0016)."""
    return [*cuts, *starts.get(rid, ())]


def _night_start(p: int) -> int:
    """Начало первой ночи, задетой половинкой p: вечер этого дня или, для утра, вечер накануне."""
    return p if p % 2 == PM else p - 1


def _days(a: int, z: int) -> str:
    return f"{day_label(a)}–{day_label(z)}" if a // 2 != z // 2 else day_label(a)


@dataclass(frozen=True)
class _Row:
    """Строка назначения в частях, как их видят читатели: (начало, конец) части, сегмент."""
    rid: int
    start_pos: int
    end_pos: int
    seg_index: int
    unit_id: int | None
    pinned: bool
    pin_unit_id: int | None = None          # объект закрепления части без объекта

    @property
    def pin_target(self) -> int | None:
        return (self.unit_id if self.unit_id is not None else self.pin_unit_id) if self.pinned else None


@dataclass
class _Info:
    """Элемент распределения для записи: брони, части расчёта, разрезы сверх границ версий."""
    rs: list[Reservation]
    number: str
    pieces: list[Piece]
    extra: set[int]
    fixed_pin: dict[int, tuple[bool, int | None]]      # часть → (закреплена, объект закрепления без объекта)
    lost: dict[int, int]                     # часть → объект строки, который ей больше не подходит
    settled: bool


def compute(db: Session) -> AllocationState:
    """Распределение без записи: им пользуются и сохранение, и снимок предпросмотра.

    Части распределения — части фонда, дополнительно разрезанные у заселённых броней по
    сегодняшнему вечеру и по началу каждого OOO на их объекте: прошлое заморожено (L1), будущее
    держит объект, пока OOO или фонд его не отнимут, и тогда переезжает один раз с ночи D до
    конца (§4.3). Лишние разрезы (объект и закрепление по обе стороны те же) при записи
    склеиваются; оставшиеся видны читателям по Assignment.start_pos."""
    today = local_date()
    morning, evening = pos(today, AM), pos(today, PM)
    res = list(db.scalars(select(Reservation).where(Reservation.status.in_(OCCUPYING),
                                                    Reservation.check_out >= today)))
    # фонд — с дня до самого раннего заезда: AM этого заезда принадлежит предыдущей версии
    first = min([today, *(r.check_in for r in res)]) - dt.timedelta(days=1)
    # OOO — и прошлые, пока в окне живут брони: наложение на прошлые части видно предупреждением
    ooo_rows = list(db.scalars(select(Ooo).where(Ooo.end >= first)))
    night_rows = db.execute(select(BlockNight.block_id, BlockNight.category_id, BlockNight.night,
                                   BlockNight.quantity, Block.title)
                            .join(Block, Block.id == BlockNight.block_id).where(BlockNight.night >= today)).all()
    last = max([today, *(r.check_out for r in res), *(h.end for h in ooo_rows),
                *(n.night + dt.timedelta(days=1) for n in night_rows)])
    timeline = fund_for(db, first, last)
    cuts = [boundary_pos(d) for d in timeline.boundaries()]
    spans = unit_spans(timeline, pos(first, AM), pos(last, PM))
    codes = {c.id: c.code for snap in timeline.snapshots() for c in snap.categories.values()}

    ooo: list[OooRef] = []                 # распределению — OOO, не закончившиеся к сегодняшнему утру
    past_ooo: list[OooRef] = []
    warnings: list[AllocWarning] = []
    members: dict[Key, list[int]] = {}
    for h in ooo_rows:
        title = h.reason or "OOO"
        hs, he = ooo_span(h.start, h.start_half, h.end, h.end_half)
        past_ooo.append(OooRef(h.unit_id, hs, he, title))
        if he < morning:
            continue
        ooo.append(OooRef(h.unit_id, hs, he, title))
        # OOO на дни, когда объекта нет в фонде (спецификация версий §14); прошлое — не тревога
        for a, z in absent_parts(spans, h.unit_id, max(hs, morning), he):
            u = timeline.unit(h.unit_id, dt.date.fromordinal(a // 2))
            label = u.label if u is not None else f"#{h.unit_id}"
            warnings.append(AllocWarning("hold_absent", ("h", h.id), 0,
                                         f"{title}: объекта {label} нет в фонде {day_label(a)}–{day_label(z)}"))
            members[("h", h.id)] = []

    moves = _moves(db, [r.id for r in res])
    groups: dict[int, list[Reservation]] = {}
    for r in res:
        if r.group_id is not None:
            groups.setdefault(r.group_id, []).append(r)
    envelopes = {gid: _envelope(rs, moves) for gid, rs in groups.items()}
    own_segs = {r.id: segments(r.check_in, r.check_out, r.early, r.late, r.category_id, moves[r.id]) for r in res}
    # строки назначений — по частям, как их режут читатели (границы версий и start_pos строк)
    rows_of: dict[int, dict[int, Assignment]] = {r.id: {} for r in res}
    starts: dict[int, list[int]] = {}
    if res:
        for a in db.scalars(select(Assignment).where(Assignment.reservation_id.in_([r.id for r in res]))):
            rows_of[a.reservation_id][a.seg_index] = a
            if a.start_pos is not None:
                starts.setdefault(a.reservation_id, []).append(a.start_pos)
    stored: dict[int, list[_Row]] = {}
    for r in res:
        stored[r.id] = [_Row(r.id, p.start_pos, p.end_pos, p.seg_index, a.unit_id, bool(a.pinned), a.pin_unit_id)
                        for p in pieces(own_segs[r.id], own_cuts(cuts, starts, r.id))
                        if (a := rows_of[r.id].get(p.index)) is not None]
    by_rid = {r.id: r for r in res}

    by_unit: dict[int, list[UnitSpan]] = {}
    for u in spans:
        by_unit.setdefault(u.unit_id, []).append(u)

    def unit_cat(uid: int, p: Piece) -> int | None:
        """Категория объекта на всей части; None — объекта нет в фонде на части целиком."""
        return next((u.category_id for u in by_unit.get(uid, ()) if u.start_pos <= p.start_pos
                     and p.end_pos <= u.end_pos), None)

    def under_ooo(uid: int, p: Piece) -> OooRef | None:
        return next((o for o in ooo if o.unit_id == uid and overlaps(o.start_pos, o.end_pos, p.start_pos, p.end_pos)),
                    None)

    items: list[AllocItem] = []
    info: dict[Key, _Info] = {}

    def add_item(key: Key, number: str, rs: list[Reservation], segs: list[Segment]) -> None:
        settled = any(r.status in FROZEN_STATUSES for r in rs)
        mine = sorted((row for r in rs for row in stored[r.id]), key=lambda row: (row.start_pos, row.rid))
        extra = {row.start_pos for row in mine if row.start_pos <= evening}     # прошлые переезды — история
        if settled:
            extra.add(evening)
            held = {row.unit_id for row in mine if row.unit_id is not None}
            lo, hi = max(segs[0].start_pos, evening), segs[-1].end_pos
            extra |= {max(evening, _night_start(o.start_pos)) for o in ooo
                      if o.unit_id in held and overlaps(o.start_pos, o.end_pos, lo, hi)}
        ps = pieces(segs, [*cuts, *extra])

        def stored_at(p: Piece) -> _Row | None:
            """Строка, чья часть содержит начало p (у группы — любого члена), иначе первая пересекающая."""
            over = [row for row in mine if overlaps(row.start_pos, row.end_pos, p.start_pos, p.end_pos)]
            return next((row for row in over if row.start_pos <= p.start_pos), over[0] if over else None)

        pins: dict[int, int] = {}
        for seg in {s.index for s in segs}:
            rows = [row for row in mine if row.seg_index == seg and row.pin_target is not None]
            live = [row for row in rows if row.end_pos >= morning]
            if rows:
                pins[seg] = (live or rows)[-1].pin_target      # как effective_pin: последняя живая часть
        fixed: dict[int, int | None] = {}
        fixed_pin: dict[int, tuple[bool, int | None]] = {}
        lost: dict[int, int] = {}
        prev: Piece | None = None
        for p in ps:
            row = stored_at(p)
            ok = row is not None and (by_rid[row.rid].status in FROZEN_STATUSES or p.end <= today)
            uid = row.unit_id if ok else None
            if p.end_pos < morning or (p.start_pos < evening and (uid is not None or settled)):
                # закончившаяся до сегодняшнего утра — заморожена и без объекта (L1); заселённая до
                # сегодняшнего вечера — в своём объекте или без объекта, как было
                kept = ok and row.pinned
                fixed[p.index] = uid
                fixed_pin[p.index] = (kept, row.pin_unit_id if kept and uid is None else None)
            elif settled and uid is not None and (prev is None or prev.seg_index != p.seg_index
                                                  or (prev.index in fixed and fixed[prev.index] is None)):
                # перед частью нет замороженной с объектом (заезд сегодня, переезд по категории,
                # прошлое без объекта): держит объект строки, пока тот есть в фонде и не под OOO
                if unit_cat(uid, p) is not None and under_ooo(uid, p) is None:
                    fixed[p.index], fixed_pin[p.index] = uid, (row.pinned, None)
                else:
                    lost[p.index] = uid
            prev = p
        # приоритет части 2 §4.2: предварительные — после подтверждённых и заселённых
        rank = 0 if any(r.status != "tentative" for r in rs) else 1
        items.append(AllocItem(key, number, tuple(ps), pins, fixed, rank=rank, in_house=settled))
        members[key] = [r.id for r in rs]
        info[key] = _Info(rs, number, ps, extra, fixed_pin, lost, settled)

    for r in res:
        if r.group_id is None:
            add_item(("r", r.id), r.number or str(r.id), [r], own_segs[r.id])
    for gid, rs in groups.items():
        add_item(("g", gid), rs[0].number or f"группа {gid}", rs, envelopes[gid])

    block_slots = slots({(n.block_id, n.category_id, n.night): n.quantity for n in night_rows},
                        {n.block_id: n.title for n in night_rows})
    # пожелания главного гостя подключает Task 5; обороты вне расчёта не нужны — все выезды с
    # сегодня есть среди броней расчёта
    got, slot_units, alloc_warnings = allocate(spans, ooo, block_slots, items, codes, {})
    warnings += alloc_warnings
    members.update({w.key: [] for w in alloc_warnings if w.key[0] == "b"})
    released = {(w.key, w.piece_index) for w in alloc_warnings if w.kind == "pin_invalid"}
    # закрепление переехало на новый объект; без объекта — остаётся прежним (§4.4)
    pinned_now = {(w.key, w.piece_index // PIECE_BASE): uid for w in alloc_warnings
                  if w.kind == "pin_conflict" and (uid := got.get((w.key, w.piece_index))) is not None}
    # бронь без объекта — и овербукинг, и категория, которой нет в фонде: обе — новая бронь без
    # объекта, проверка права stays.overbook видит их одинаково (§7)
    overbooked = {(w.key, w.piece_index) for w in alloc_warnings if w.kind in ("overbooked", "category_missing")}

    out_units: dict[tuple[int, int], int | None] = {}
    out_pinned: dict[tuple[int, int], bool] = {}
    out_pin_units: dict[tuple[int, int], int] = {}
    out_spans: dict[tuple[int, int], tuple[int, int]] = {}
    out_overbooked: set[tuple[int, int]] = set()
    for it in items:
        inf = info[it.key]
        state: dict[int, tuple[int | None, bool, int | None]] = {}
        for p in inf.pieces:
            if p.index in it.fixed:
                state[p.index] = (it.fixed[p.index], *inf.fixed_pin[p.index])
                continue
            uid = got.get((it.key, p.index))
            seg = p.seg_index
            # закреплена часть в объекте закрепления — прежнем или перенесённом (pin_conflict); часть
            # заселённого, удержанная в другом объекте до переезда, — нет
            pin = pinned_now.get((it.key, seg), it.pinned.get(seg))
            held = pin is not None and (it.key, p.index) not in released
            if uid is None and held:
                state[p.index] = (None, True, pin)       # овербукинг закреплённой — закрепление сохранено
            else:
                state[p.index] = (uid, held and uid == pin, None)
        _place_warnings(it, inf, got, timeline, unit_cat, under_ooo, past_ooo, warnings)
        # разрезы, по обе стороны которых объект и закрепление те же, не хранятся
        keep = []
        for left, right in zip(inf.pieces, inf.pieces[1:], strict=False):
            if (right.start_pos in inf.extra and left.seg_index == right.seg_index
                    and state[left.index] != state[right.index]):
                keep.append(right.start_pos)
        final = [*cuts, *keep]
        for r in inf.rs:
            for mp in pieces(own_segs[r.id], final):
                p = next((q for q in inf.pieces if q.start_pos <= mp.start_pos <= q.end_pos), None)
                if p is None:
                    continue
                out_units[(r.id, mp.index)], out_pinned[(r.id, mp.index)], pin_unit = state[p.index]
                if pin_unit is not None:
                    out_pin_units[(r.id, mp.index)] = pin_unit
                out_spans[(r.id, mp.index)] = (mp.start_pos, mp.end_pos)
                if (it.key, p.index) in overbooked:
                    lo, hi = max(mp.start_pos, p.start_pos), min(mp.end_pos, p.end_pos)
                    out_overbooked |= {(r.id, n) for n in range(lo // 2, hi // 2 + 1) if lo <= 2 * n + 1 <= hi}
    return AllocationState(out_units, out_pinned, warnings, members, out_spans, slot_units,
                           frozenset(out_overbooked), out_pin_units)


def _place_warnings(it: AllocItem, inf: _Info, got, timeline: FundTimeline, unit_cat, under_ooo,
                    past_ooo: list[OooRef], warnings: list[AllocWarning]) -> None:
    """Переезд заселённой брони (фонд или OOO с ночи D) и наложение OOO на прошлые части."""
    def label(uid: int | None, p: Piece) -> str | None:
        u = timeline.unit(uid, p.start) if uid is not None else None
        return u.label if u is not None else None

    for p in inf.pieces:
        uid = it.fixed.get(p.index)
        if p.index not in it.fixed or uid is None:
            continue
        for o in past_ooo:
            if o.unit_id == uid and overlaps(o.start_pos, o.end_pos, p.start_pos, p.end_pos):
                a, z = max(o.start_pos, p.start_pos), min(o.end_pos, p.end_pos)
                warnings.append(AllocWarning(
                    "ooo_overlap", it.key, p.index,
                    f"Бронь {inf.number}: объект {label(uid, p) or uid} в OOO «{o.title}» {_days(a, z)} — "
                    f"прошлые дни проживания не переселяются"))
    if not inf.settled:
        return
    prev: Piece | None = None
    for p in inf.pieces:
        same = prev is not None and prev.seg_index == p.seg_index
        ref = (got.get((it.key, prev.index)) if same else None) if p.index not in inf.lost else inf.lost[p.index]
        prev = p
        if p.index in it.fixed or ref is None or p.seg_index in it.pinned:
            continue              # у закреплённого сегмента о переезде скажет pin_invalid / pin_conflict
        new = got.get((it.key, p.index))
        if new == ref:
            continue
        where = "переезд в " + (label(new, p) or str(new)) if new is not None else "без объекта"
        o = under_ooo(ref, p) if unit_cat(ref, p) == p.category_id else None
        if o is None:
            warnings.append(AllocWarning(
                "unit_invalid", it.key, p.index,
                f"Бронь {inf.number}: объект {label(ref, p) or ref} не подходит по фонду с "
                f"{p.start.strftime('%d.%m')} — {where}"))
        else:
            warnings.append(AllocWarning(
                "ooo_move", it.key, p.index,
                f"Бронь {inf.number} (заселена): объект {label(ref, p) or ref} — OOO «{o.title}» с "
                f"{day_label(max(o.start_pos, p.start_pos))} — {where} с {p.start.strftime('%d.%m')} до выезда"))


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
        a.start_pos = state.spans[(rid, piece)][0]
        a.pin_unit_id = state.pin_units.get((rid, piece))
    db.flush()
    db.info[CACHE_KEY] = state
    return state


def current_state(db: Session) -> AllocationState:
    """Состояние после последней записи в этой сессии, иначе — свежий расчёт."""
    return db.info.get(CACHE_KEY) or compute(db)


def warnings_for(state: AllocationState, rid: int) -> list[str]:
    keys = {k for k, rids in state.members.items() if rid in rids}
    return [w.text for w in state.warnings if w.key in keys]
