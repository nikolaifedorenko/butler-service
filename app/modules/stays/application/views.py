"""Чтение видов «Шахматки» (§6): шахматка объектов, карточка брони. Загрузка пакетами —
число запросов не зависит от числа объектов и броней (бюджет SQL — §10)."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import local_date

from ..adapters.orm import (
    Assignment,
    BlockNight,
    Companion,
    Guest,
    Label,
    Logistics,
    Move,
    Occupant,
    Ooo,
    Reservation,
)
from ..domain.allocate import natural_key
from ..domain.halfday import PIECE_BASE, PM, Piece, ooo_span, pieces, pos, segments
from ..ports.duty import DutyPort
from . import allocation, family
from .context import butlers_on, load_context, nights
from .fund_versions import (
    CategoryInfo,
    FundSnapshot,
    FundTimeline,
    UnitInfo,
    fund_day,
    fund_for,
    fund_for_stays,
    version_cuts,
)
from .guests import search_query, short_name
from .reservations import STATUS_TITLES
from .visibility import Level, at_least, serialize_bar

MAX_DAYS = 62
LEVEL_RANK = {"regular": 0, "vip": 1, "vvip": 2}


class ViewError(ValueError):
    """Ошибка параметров вида → 422."""


@dataclass(frozen=True)
class BoardFilters:
    """Фильтры видов (§7): внутри измерения — «или», между измерениями — «и», флаги — все сразу.
    Узлы, категории, виды и флаги проверяются по фонду каждого дня (fund_match)."""
    group_ids: tuple[int, ...] = ()         # узлы дерева фонда: объекты их веток
    category_ids: tuple[int, ...] = ()
    flag_ids: tuple[int, ...] = ()
    kind_ids: tuple[int, ...] = ()          # виды категорий (справочник)
    floor: str | None = None
    escorted_only: bool = False
    vip: bool = False
    employee_id: int | None = None          # «кто ведёт» — с задачи 14
    q: str = ""

    def for_level(self, level: Level) -> BoardFilters:
        """Поиск и VIP опираются на данные гостей: уровню occupancy они не применяются (находка
        C1 аудита) — иначе по ответу можно было бы подобрать фамилию или уровень гостя."""
        return self if level != "occupancy" else replace(self, q="", vip=False, employee_id=None)


def fund_match(snap: FundSnapshot, unit_id: int | None, category_id: int | None, f) -> bool:
    """Проходит ли объект фильтры фонда (узел, категория, вид, флаги, этаж) в снимке дня.
    f — BoardFilters или DayFilters. Объекта нет в фонде дня — не проходит. Бронь без объекта
    (unit_id None) проверяется по категории; узел, флаги и этаж у неё не определены."""
    u = snap.units.get(unit_id) if unit_id is not None else None
    if unit_id is not None and u is None:
        return False
    if u is None and (f.group_ids or f.flag_ids or f.floor):
        return False
    cid = u.category_id if u is not None else category_id
    cat = snap.categories.get(cid)
    return ((not f.group_ids or bool(set(f.group_ids) & set(snap.unit_path(unit_id))))
            and (not f.category_ids or cid in f.category_ids)
            and (not f.kind_ids or (cat is not None and cat.kind_id in f.kind_ids))
            and (not f.flag_ids or set(f.flag_ids) <= u.flags)
            and (not f.floor or u.floor == f.floor))


def check_window(first: dt.date, last: dt.date) -> list[dt.date]:
    if last < first:
        raise ViewError("Конец периода раньше начала")
    if (last - first).days + 1 > MAX_DAYS:
        raise ViewError(f"Период шахматки — не больше {MAX_DAYS} дней")
    return [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]


def _d(v: dt.date | None) -> str | None:
    return v.isoformat() if v else None


def _top_level(levels) -> str:
    return max(levels, key=lambda lv: LEVEL_RANK[lv], default="regular")


@dataclass
class BoardRow:
    """Строка шахматки — постоянный объект. Свойства — на первый день периода, когда он в
    фонде; смены обозначения и категории — по датам; дни «нет в фонде» и «вне фильтра» — off."""
    info: UnitInfo
    category: CategoryInfo
    group_path: tuple[int, ...]
    group: str                              # путь узла названиями: «Корпус / Блок B»
    labels: list[tuple[dt.date, str]]
    categories: list[tuple[dt.date, int]]
    in_fund: list[dt.date] = field(default_factory=list)       # дни периода, когда объект в фонде
    off: list[list] = field(default_factory=list)              # [первый, последний, причина]

    @property
    def id(self) -> int:
        return self.info.id

    @property
    def label(self) -> str:
        return self.info.label


def _passing(snap: FundSnapshot, f: BoardFilters) -> set[int]:
    """Объекты снимка, прошедшие фильтры фонда (и «с сопровождением» — по категории)."""
    return {uid for uid, u in snap.units.items() if fund_match(snap, uid, None, f)
            and (not f.escorted_only or getattr(snap.categories.get(u.category_id), "escorted", False))}


def _runs(marks: list[str | None], days: list[dt.date]) -> list[list]:
    """Подряд идущие дни с одной причиной → [первый, последний, причина]."""
    out: list[list] = []
    for d, m in zip(days, marks, strict=True):
        if m is None:
            continue
        if out and out[-1][2] == m and out[-1][1] == _d(d - dt.timedelta(days=1)):
            out[-1][1] = _d(d)
        else:
            out.append([_d(d), _d(d), m])
    return out


def _board_rows(fund: FundTimeline, days: list[dt.date], f: BoardFilters) -> list[BoardRow]:
    """Объекты, прошедшие фильтр хотя бы в один день периода — каждый день по фонду этого дня
    (§7: флаг с 15.11 — в фильтре с 15.11). Остальные дни строки — off: «absent» (нет в фонде)
    или «filtered» (в фонде, но вне фильтра); полосы и блоки этих дней не скрываются."""
    if not fund.parts:
        return []
    uids = list(dict.fromkeys(uid for snap in fund.snapshots() for uid in snap.units))
    passing: dict[int, set[int]] = {}
    rows: dict[int, BoardRow] = {}
    marks: dict[int, list[str | None]] = {uid: [] for uid in uids}
    for d in days:
        snap = fund.on(d)
        if snap.version_id not in passing:
            passing[snap.version_id] = _passing(snap, f)
        ok = passing[snap.version_id]
        for uid in uids:
            u = snap.units.get(uid)
            if u is None:
                marks[uid].append("absent")
                continue
            marks[uid].append(None if uid in ok else "filtered")
            row = rows.get(uid)
            if row is None:
                path = snap.unit_path(uid)
                rows[uid] = row = BoardRow(u, snap.categories[u.category_id], path,
                                           " / ".join(snap.path_titles(u.group_id)) if path else "",
                                           [(d, u.label)], [(d, u.category_id)])
            else:
                if row.labels[-1][1] != u.label:
                    row.labels.append((d, u.label))
                if row.categories[-1][1] != u.category_id:
                    row.categories.append((d, u.category_id))
            row.in_fund.append(d)
    out = []
    for uid, row in rows.items():
        if None in marks[uid]:
            row.off = _runs(marks[uid], days)
            out.append(row)
    return sorted(out, key=lambda b: (b.category.sort_order, natural_key(b.label), b.id))


def _glued(ps: list[Piece], unit_of) -> list[list[Piece]]:
    """Соседние части одного сегмента с тем же объектом — одна полоса (граница версии фонда,
    не сменившая объект, на шахматке не видна)."""
    runs: list[list[Piece]] = []
    for p in ps:
        if runs and runs[-1][-1].seg_index == p.seg_index and unit_of(runs[-1][-1]) == unit_of(p):
            runs[-1].append(p)
        else:
            runs.append([p])
    return runs


@dataclass
class _Stays:
    """Брони диапазона, занимающие объекты, с переездами, объектами частей и составом — пакетом."""
    res: list[Reservation]
    moves: dict[int, list]
    asg: dict[tuple[int, int], int | None]
    occ: dict[int, list[Occupant]]
    segs: dict[int, list]
    parts: dict[int, list[Piece]]           # части сегментов (границы версий фонда)


def _load_stays(db: Session, first: dt.date, last: dt.date, cuts: list[int]) -> _Stays:
    res = list(db.scalars(select(Reservation).where(Reservation.status.in_(allocation.OCCUPYING),
                                                    Reservation.check_in <= last,
                                                    Reservation.check_out >= first)))
    rids = [r.id for r in res]
    moves: dict[int, list] = {rid: [] for rid in rids}
    asg: dict[tuple[int, int], int | None] = {}
    starts: dict[int, list[int]] = {}
    occ: dict[int, list[Occupant]] = {rid: [] for rid in rids}
    if rids:
        for m in db.scalars(select(Move).where(Move.reservation_id.in_(rids))):
            moves[m.reservation_id].append((m.move_date, m.category_id))
        for a in db.scalars(select(Assignment).where(Assignment.reservation_id.in_(rids))):
            asg[(a.reservation_id, a.seg_index)] = a.unit_id
            if a.start_pos is not None:
                starts.setdefault(a.reservation_id, []).append(a.start_pos)
        for o in db.scalars(select(Occupant).where(Occupant.reservation_id.in_(rids))
                            .order_by(Occupant.date_from, Occupant.id)):
            occ[o.reservation_id].append(o)
    segs = {r.id: segments(r.check_in, r.check_out, r.early, r.late, r.category_id, moves[r.id]) for r in res}
    return _Stays(res, moves, asg, occ, segs,
                  {r.id: pieces(segs[r.id], allocation.own_cuts(cuts, starts, r.id)) for r in res})


def _occupied(st: _Stays, first: dt.date, last: dt.date) -> dict[tuple[int, dt.date], int]:
    """(объект, ночь) → бронь. Ночь d брони — её часть, покрывающая вечер d (как ctx.unit_of)."""
    one = dt.timedelta(days=1)
    out: dict[tuple[int, dt.date], int] = {}
    for r in st.res:
        for p in st.parts[r.id]:
            uid = st.asg.get((r.id, p.index))
            if uid is None:
                continue
            d, end = max(p.start, r.check_in, first), min(p.end, r.check_out - one, last)
            while d <= end:
                if p.start_pos <= pos(d, PM) <= p.end_pos:
                    out[(uid, d)] = r.id
                d += one
    return out


def _load(row: BoardRow, occupied: dict[tuple[int, dt.date], int]) -> float:
    """Загрузка строки за период: занятые ночи / ночи в фонде, 0..1."""
    if not row.in_fund:
        return 0.0
    return round(sum((row.id, d) in occupied for d in row.in_fund) / len(row.in_fund), 3)


def units_board(db: Session, first: dt.date, last: dt.date, f: BoardFilters, level: Level) -> dict:
    days = check_window(first, last)
    f = f.for_level(level)
    fund = fund_for(db, first, last)
    units = _board_rows(fund, days, f)
    unit_ids = {u.id for u in units}
    visible_cats = {cid for u in units for _, cid in u.categories}
    cuts = version_cuts(db)
    st = _load_stays(db, first, last, cuts)
    res, asg, occ = st.res, st.asg, st.occ
    occupied = _occupied(st, first, last)
    names = level != "occupancy"
    guests = {}
    labels = {}
    if names:
        gids = {o.guest_id for os in occ.values() for o in os}
        guests = {g.id: g for g in db.scalars(select(Guest).where(Guest.id.in_(gids)))} if gids else {}
        labels = {lb.id: lb for lb in db.scalars(select(Label))}
    match = _search(f.q, res, occ, guests, units, asg) if f.q.strip() else None
    today = local_date()
    on_duty: dict[int, list[str]] = {}
    if names and first <= today <= last:
        on_duty = butlers_on(db, today, res, st.parts, asg, occ, guests, fund)

    bars = []
    for r in res:
        if match is not None and r.id not in match:
            continue
        rocc = occ[r.id]
        top = _top_level(guests[o.guest_id].level for o in rocc if o.guest_id in guests)
        if f.vip and top == "regular":
            continue
        segs = st.segs[r.id]
        mains = [o for o in rocc if o.role == "main"]
        on_day = max(r.check_in, first)
        main_now = next((o for o in mains if o.date_from <= on_day < o.date_to), mains[0] if mains else None)
        lb = labels.get(r.label_id)
        base = {"reservation_id": r.id, "status": r.status, "guests_count": len({o.guest_id for o in rocc}),
                "number": r.number, "label": {"title": lb.title, "color": lb.color} if lb else None,
                "main_guest": short_name(guests[main_now.guest_id]) if main_now and main_now.guest_id in guests else "",
                "mains": [{"guest": short_name(guests[o.guest_id]), "from": _d(o.date_from), "to": _d(o.date_to)}
                          for o in mains if o.guest_id in guests],
                "level": top, "butlers_today": on_duty.get(r.id, []),
                "customer": r.customer, "paid_category_id": r.paid_category_id or r.category_id,
                "note": r.note, "declined_butler": r.declined_butler, "fields": json.loads(r.fields_json or "{}")}
        # полоса — соседние части сегмента с одним объектом; seg_index полосы — индекс её первой
        # части (seg_index // PIECE_BASE — сегмент; 0 — начало брони)
        for run in _glued(st.parts[r.id], lambda p, rid=r.id: asg.get((rid, p.index))):
            p0, p1 = run[0], run[-1]
            uid = asg.get((r.id, p0.index))
            if uid not in unit_ids and not (uid is None and p0.category_id in visible_cats):
                continue
            bars.append(serialize_bar({**base, "seg_index": p0.index, "unit_id": uid, "category_id": p0.category_id,
                                       "start": _d(p0.start), "end": _d(p1.end), "start_pos": p0.start_pos,
                                       "end_pos": p1.end_pos, "early": r.early and p0.index == 0,
                                       "late": r.late and p1.end_pos == segs[-1].end_pos}, level))

    holds = [{"id": h.id, "unit_id": h.unit_id, "start": _d(h.start), "end": _d(h.end), "kind": "ooo",
              "start_half": h.start_half, "end_half": h.end_half,
              # причина OOO — свободный текст (в нём бывает фамилия): только с уровня names
              "title": h.reason if names else "",
              **dict(zip(("start_pos", "end_pos"), ooo_span(h.start, h.start_half, h.end, h.end_half), strict=True))}
             for h in db.scalars(select(Ooo).where(Ooo.start <= last, Ooo.end >= first))
             if h.unit_id in unit_ids]
    warnings = []
    if names:
        state = allocation.current_state(db)
        shown = {b["reservation_id"] for b in bars}
        shown_holds = {("h", h["id"]) for h in holds}
        # нехватка блока (block_short) — без броней: по ночам периода и категории фильтра
        # (у неё piece_index — ordinal первой ночи, last — последней)
        def block_short(w) -> bool:
            return (w.kind == "block_short" and w.piece_index <= last.toordinal() and w.last >= first.toordinal()
                    and (not f.category_ids or w.category_id in f.category_ids))
        warnings = [{"kind": w.kind, "reservation_ids": state.members[w.key], "text": w.text}
                    for w in state.warnings if shown & set(state.members[w.key]) or w.key in shown_holds
                    or block_short(w)]
    return {"days": [_d(d) for d in days], "visibility": level,
            "units": [{"unit_id": u.id, "label": u.label,
                       "labels": [{"from": _d(d), "label": lb} for d, lb in u.labels],
                       "category_id": u.info.category_id, "category": u.category.code,
                       "categories": [{"from": _d(d), "category_id": cid} for d, cid in u.categories],
                       "group_path": list(u.group_path), "group": u.group, "floor": u.info.floor,
                       "flags": sorted(u.info.flags), "load": _load(u, occupied), "off": u.off}
                      for u in units],
            "bars": bars, "holds": holds, "warnings": warnings}


def _search(q: str, res, occ, guests, units, asg) -> set[int]:
    needle = search_query(q)
    hits = {r.id for r in res if needle in (r.search_text or "")}
    hits |= {rid for rid, os in occ.items() if any(needle in (guests[o.guest_id].search_text or "")
                                                   for o in os if o.guest_id in guests)}
    unit_hit = {u.id for u in units if needle in u.label.lower()}
    hits |= {rid for (rid, _), uid in asg.items() if uid in unit_hit}
    return hits


def card_coverage(db: Session, r: Reservation, duty: DutyPort | None) -> list[dict]:
    """Покрытие брони по ночам: кто кого ведёт и предупреждения дня против Графика (§4.4)."""
    ctx = load_context(db, r.check_in, r.check_out - dt.timedelta(days=1), duty)
    out = []
    for d in nights(r.check_in, r.check_out):
        cover = ctx.cover(d)
        who: dict[int, list[int]] = {}
        for (rid, g), emps in cover.by_guest.items():
            if rid == r.id:
                for e in emps:
                    who.setdefault(e, []).append(g)
        lines = [ln for ln in ctx.lines_on(d) if ln.reservation_id == r.id
                 or (ln.group_id is not None and ln.group_id == r.group_id)]
        butlers = [{"employee_id": e, "name": ctx.name(e), "guest_ids": sorted(gs),
                    "line_id": next((ln.id for ln in lines if ln.employee_id == e), None),
                    "overnight": any(ln.overnight for ln in lines if ln.employee_id == e)}
                   for e, gs in sorted(who.items())]
        mine = set(who)
        warns = [{"kind": w.kind, "employee_id": w.employee_id, "text": ctx.warning_text(w)}
                 for w in ctx.warnings(d) if w.reservation_id == r.id
                 or (w.reservation_id is None and w.employee_id in mine)]
        out.append({"day": d.isoformat(), "butlers": butlers, "warnings": warns})
    return out


def _relatives_in_house(db: Session, r: Reservation, guests: dict[int, Guest]) -> dict[int, list[dict]]:
    """Родственники гостей брони среди всех, кто проживает в те же даты (§4)."""
    if not guests:
        return {}
    present = set(db.scalars(select(Occupant.guest_id).join(Reservation, Reservation.id == Occupant.reservation_id)
                             .where(Reservation.status.in_(allocation.OCCUPYING),
                                    Occupant.date_from < r.check_out, Occupant.date_to > r.check_in)))
    kin = family.kin_among(db, present | set(guests), set(guests))
    others = {o for rel in kin.values() for o, _ in rel} - set(guests)
    known = {**{g.id: g for g in db.scalars(select(Guest).where(Guest.id.in_(others)))}, **guests} if others else guests
    return {gid: [{"guest_id": o, "title": t, "name": short_name(known[o])} for o, t in rel] for gid, rel in kin.items()}


def reservation_card(db: Session, rid: int, level: Level, duty: DutyPort | None = None) -> dict:
    """Карточка брони (§6.5): уровень «с фамилиями» — состав по датам; «полный» — плюс
    заказчик, примечания, сопровождающие, логистика, настраиваемые поля."""
    r = db.get(Reservation, rid)
    if r is None:
        raise LookupError("Бронь не найдена")
    moves = sorted((m.move_date, m.category_id) for m in db.scalars(select(Move).where(Move.reservation_id == rid)))
    # объект сегмента — его первой части (части режутся границами версий фонда)
    asg = {a.seg_index // PIECE_BASE: a.unit_id for a in db.scalars(
        select(Assignment).where(Assignment.reservation_id == rid)) if a.seg_index % PIECE_BASE == 0}
    fund = fund_for_stays(db, r.check_in, r.check_out)
    segs = segments(r.check_in, r.check_out, r.early, r.late, r.category_id, moves)
    category = fund.category(r.category_id, r.check_in)
    occ = list(db.scalars(select(Occupant).where(Occupant.reservation_id == rid)
                          .order_by(Occupant.date_from, Occupant.id)))
    guests = {g.id: g for g in db.scalars(select(Guest).where(Guest.id.in_({o.guest_id for o in occ})))} if occ else {}
    paid_id = r.paid_category_id or r.category_id
    paid = fund.category(paid_id, r.check_in)
    paid_code = paid.code if paid else "?"
    lb = db.get(Label, r.label_id) if r.label_id else None
    relatives = _relatives_in_house(db, r, guests) if at_least(level, "names") else {}
    card = {
        "id": r.id, "number": r.number, "status": r.status, "status_title": STATUS_TITLES[r.status],
        "check_in": _d(r.check_in), "check_out": _d(r.check_out), "early": r.early, "late": r.late,
        "category": category.code if category else "?",
        "paid_category_id": paid_id, "paid_category": paid_code,
        "upgrade": f"апгрейд: оплачена {paid_code}" if paid_id != r.category_id else "",
        "label": {"title": lb.title, "color": lb.color} if lb else None,
        "group_id": r.group_id, "version": r.version,
        "segments": [{"index": s.index, "start": _d(s.start), "end": _d(s.end), "unit_id": asg.get(s.index),
                      "unit": u.label if (u := fund.unit(asg.get(s.index), fund_day(s.start_pos))) else None}
                     for s in segs],
        "occupants": [{"guest_id": o.guest_id, "guest": short_name(guests[o.guest_id]),
                       "level": guests[o.guest_id].level, "date_from": _d(o.date_from),
                       "date_to": _d(o.date_to), "role": o.role,
                       "relatives": relatives.get(o.guest_id, [])} for o in occ if o.guest_id in guests],
        "coverage": card_coverage(db, r, duty) if r.status in allocation.OCCUPYING else [
            {"day": d.isoformat(), "butlers": [], "warnings": []} for d in nights(r.check_in, r.check_out)],
    }
    if at_least(level, "full"):
        card |= {"customer": r.customer, "note": r.note,
                 "declined_butler": r.declined_butler, "fields": json.loads(r.fields_json or "{}"),
                 "companions": [{"kind": c.kind, "description": c.description} for c in
                                db.scalars(select(Companion).where(Companion.reservation_id == rid))],
                 "logistics": [{"kind": lg.kind, "date": _d(lg.date), "time": lg.time, "description": lg.description}
                               for lg in db.scalars(select(Logistics).where(Logistics.reservation_id == rid)
                                                    .order_by(Logistics.date, Logistics.id))]}
    return card


NO_GROUP = "Без группы"
TOTAL = "Итого по выбранному"


def _nodes(fund: FundTimeline, f: BoardFilters) -> list[tuple[int | None, tuple[str, ...]]]:
    """Узлы «Загрузки»: выбранные в фильтре «Где», иначе корневые узлы дерева (и «Без группы»,
    если в периоде есть объекты без узла). Путь названиями — по первой версии, где узел есть."""
    snaps = fund.snapshots()
    if f.group_ids:
        out = []
        for gid in dict.fromkeys(f.group_ids):
            snap = next((s for s in snaps if gid in s.groups), None)
            if snap is not None:
                out.append((gid, snap.path_titles(gid)))
        return out
    roots: dict[int, tuple[int, str]] = {}
    for s in snaps:
        for g in s.groups.values():
            if g.parent_id is None and g.id not in roots:
                roots[g.id] = (g.sort_order, g.title)
    out = [(gid, (title,)) for gid, (_o, title) in sorted(roots.items(), key=lambda x: (x[1], x[0]))]
    if any(not s.unit_path(uid) for s in snaps for uid in s.units):
        out.append((None, (NO_GROUP,)))
    return out


def _pct(living: int, blocks: int, total: int, ooo: int) -> float | None:
    """Загрузка, % (§6.1) = (проживают + блоки) / (всего − OOO); знаменатель 0 — None."""
    return round((living + blocks) / (total - ooo), 3) if total - ooo > 0 else None


def occupancy_grid(db: Session, first: dt.date, last: dt.date, f: BoardFilters) -> dict:
    """Сводная загрузка (§6.1): узлы дерева × дни и «Итого по выбранному» (объекты всех узлов —
    без двойного счёта, если выбраны узел и его потомок). Всё — по фонду дня; данных гостей
    нет, только числа: поиск и VIP не применяются."""
    days = check_window(first, last)
    one = dt.timedelta(days=1)
    f = f.for_level("occupancy")
    fund = fund_for(db, first - one, last)           # выезд в first — по объекту ночи накануне
    if not fund.parts:
        empty = dict.fromkeys(("total", "living", "guests", "arrivals", "departures", "free", "ooo", "blocks"), 0)
        return {"days": [_d(d) for d in days], "nodes": [],
                "total": {"group_id": None, "path": [TOTAL], "days": [{**empty, "pct": None} for _ in days]}}
    nodes = _nodes(fund, f)
    st = _load_stays(db, first - one, last, version_cuts(db))
    occupied = _occupied(st, first - one, last)
    unit_of = {(rid, d): uid for (uid, d), rid in occupied.items()}
    # временный адаптер (до Task 2–4): OOO занимает объект в каждый день своего интервала (хотя бы
    # половина суток); блоки не размещаются по объектам — «Блоки» = сумма количеств на ночь
    ooo_days: set[tuple[int, dt.date]] = set()
    for h in db.scalars(select(Ooo).where(Ooo.start <= last, Ooo.end >= first)):
        d = max(h.start, first)
        while d <= min(h.end, last):
            ooo_days.add((h.unit_id, d))
            d += one
    block_qty: dict[tuple[int, dt.date], int] = {}
    for cid, night, qty in db.execute(select(BlockNight.category_id, BlockNight.night, BlockNight.quantity)
                                      .where(BlockNight.night >= first, BlockNight.night <= last)):
        block_qty[(cid, night)] = block_qty.get((cid, night), 0) + qty
    arrive: dict[dt.date, list[int | None]] = {}
    leave: dict[dt.date, list[int | None]] = {}
    for r in st.res:                                   # выезд + заезд в тот же объект — в обеих строках
        arrive.setdefault(r.check_in, []).append(unit_of.get((r.id, r.check_in)))
        leave.setdefault(r.check_out, []).append(unit_of.get((r.id, r.check_out - one)))

    def people(rid: int, d: dt.date) -> int:
        return len({o.guest_id for o in st.occ[rid] if o.date_from <= d < o.date_to}) or 1

    memo: dict[tuple[int, int | None], set[int]] = {}

    def members(snap: FundSnapshot, gid: int | None) -> set[int]:
        key = (snap.version_id, gid)
        if key not in memo:
            ok = _passing(snap, f)
            memo[key] = ({u for u in ok if gid in snap.unit_path(u)} if gid is not None
                         else {u for u in ok if not snap.unit_path(u)})
        return memo[key]

    def cell(units: set[int], before: set[int], d: dt.date, snap: FundSnapshot) -> dict:
        living = [u for u in units if (u, d) in occupied]
        ooo = sum((u, d) in ooo_days for u in units)
        blocks = sum(block_qty.get((cid, d), 0) for cid in {snap.units[u].category_id for u in units if u in snap.units})
        total = len(units)
        return {"total": total, "living": len(living),
                "guests": sum(people(occupied[(u, d)], d) for u in living),
                "arrivals": sum(u in units for u in arrive.get(d, ())),
                "departures": sum(u in before for u in leave.get(d, ())),
                "free": max(0, total - len(living) - ooo - blocks), "ooo": ooo, "blocks": blocks,
                "pct": _pct(len(living), blocks, total, ooo)}

    rows = {gid: [] for gid, _ in nodes}
    total_days = []
    for d in days:
        snap, prev = fund.on(d), fund.on(d - one)
        every, every_prev = set(), set()
        for gid, _ in nodes:
            now, before = members(snap, gid), members(prev, gid)
            every |= now
            every_prev |= before
            rows[gid].append(cell(now, before, d, snap))
        total_days.append(cell(every, every_prev, d, snap))
    return {"days": [_d(d) for d in days],
            "total": {"group_id": None, "path": [TOTAL], "days": total_days},
            "nodes": [{"group_id": gid, "path": list(path), "days": rows[gid]} for gid, path in nodes]}
