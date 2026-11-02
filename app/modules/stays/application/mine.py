"""«Мои гости» и правка своих броней и гостей батлером (часть 4 §2–§4: stays.mine,
stays.mine_guest_edit, stays.mine_res_edit).

«Своя» бронь — та, где у батлера есть строка покрытия (на бронь или на её группу) за всё время:
в прошлом, сейчас, в будущем, в том числе на подмене; предварительные — тоже. «Свой» гость — тот,
кого батлер ведёт хоть одну ночь (явный список гостей сильнее строки «вся бронь / группа», как в
domain/coverage.resolve_day), или кого он сам завёл через семейное дерево. Батлер меняет только
состав (проживающих, кроме главного), логистику, сопровождающих, примечание и настраиваемые
поля; в профиле своих гостей — предпочтения, особые даты, поля и примечание. Принадлежность
проверяется на каждом запросе."""
from __future__ import annotations

import datetime as dt
import json
from itertools import groupby

from sqlalchemy import and_, exists, func, or_, select, union
from sqlalchemy.orm import Session, aliased

from app.core.time import local_date

from ..adapters.orm import (
    CoverageGuest,
    CoverageLine,
    Guest,
    GuestLink,
    Logistics,
    Occupant,
    Reservation,
)
from ..domain.allocate import natural_key
from ..domain.halfday import AM, PM, pos
from ..ports.duty import DutyPort
from . import allocation, family
from .context import load_context
from .family import full_name
from .fund import FundError
from .guests import (
    format_phone,
    guest_dict,
    guest_search_column,
    links_of,
    search_guests,
    short_name,
    text_search,
)
from .guests_list import days_to_birthday
from .history import guest_led_history
from .reservations import guest_profile_extra
from .vip_codes import code_texts

LOCKED = ("number", "check_in", "check_out", "early", "late", "category_id", "label_id", "customer",
          "paid_category_id", "escort_mode", "vip_code_id", "group_id")
GUEST_FREE = ("preferences", "special_dates", "fields", "note")
MINE_TEXT = "Батлер может менять только состав, логистику и сведения о гостях"


class MineForbidden(FundError):
    """Чужая бронь или поле, которое батлеру менять нельзя → 403."""


def _targets(line, res):
    """Строка покрытия относится к брони: прямо или через группу, где у брони в этот день ночь."""
    return or_(res.id == line.reservation_id,
               and_(line.group_id.is_not(None), res.group_id == line.group_id,
                    res.check_in <= line.day, line.day < res.check_out))


def _my_line_res(employee_id: int):
    """(строка батлера, бронь, к которой она относится) — за всё время."""
    ln, r = aliased(CoverageLine), aliased(Reservation)
    q = (select(ln, r).join(r, _targets(ln, r))
         .where(ln.employee_id == employee_id, r.status.in_(allocation.OCCUPYING)))
    return q, ln, r


def my_reservation_ids(db: Session, employee_id: int) -> set[int]:
    q, _ln, r = _my_line_res(employee_id)
    return set(db.scalars(q.with_only_columns(r.id).distinct()))


def _guest_ids_query(employee_id: int):
    """Гости явных списков батлера (строка на живую бронь или ночь группы — как у «вся бронь»);
    проживающие ночи, которую батлер ведёт строкой «вся бронь / группа», если в ту ночь их явно
    не ведёт другая строка (по брони или её группе); профили, которые батлер завёл сам."""
    eq, eln, _er = _my_line_res(employee_id)
    explicit = (eq.with_only_columns(CoverageGuest.guest_id)
                .join(CoverageGuest, CoverageGuest.coverage_id == eln.id))
    q, ln, r = _my_line_res(employee_id)
    o, x = aliased(Occupant), aliased(CoverageLine)
    whole = (q.with_only_columns(o.guest_id)
             .join(o, and_(o.reservation_id == r.id, o.date_from <= ln.day, ln.day < o.date_to))
             .where(~exists().where(CoverageGuest.coverage_id == ln.id),
                    ~select(x.id).join(CoverageGuest, CoverageGuest.coverage_id == x.id).where(
                        x.day == ln.day, CoverageGuest.guest_id == o.guest_id,
                        or_(x.reservation_id == r.id, and_(x.group_id.is_not(None), x.group_id == r.group_id)))
                    .exists()))
    created = select(Guest.id).where(Guest.created_by_employee_id == employee_id)
    return union(explicit, whole, created)


def my_guest_ids(db: Session, employee_id: int) -> set[int]:
    return set(db.scalars(_guest_ids_query(employee_id)))


def search_my_guests(db: Session, employee_id: int, q: str, full: bool) -> list[Guest]:
    """Подбор гостя среди своих (редактор связей батлера): связать можно только своих (§3);
    ниже полного уровня — только по ФИО (решение 8)."""
    return search_guests(db, q, within=_guest_ids_query(employee_id), full=full)


def owns_reservation(db: Session, employee_id: int, reservation_id: int) -> bool:
    q, _ln, r = _my_line_res(employee_id)
    return db.scalar(select(exists(q.where(r.id == reservation_id)))) or False


def owns_guest(db: Session, employee_id: int, guest_id: int) -> bool:
    return db.scalar(select(Guest.id).where(Guest.id == guest_id,
                                            Guest.id.in_(_guest_ids_query(employee_id)))) is not None


def owned_among(db: Session, employee_id: int, ids: set[int]) -> set[int]:
    """Кто из ids — свой гость батлера (тот же запрос, что owns_guest)."""
    if not ids:
        return set()
    return set(db.scalars(select(Guest.id).where(Guest.id.in_(ids), Guest.id.in_(_guest_ids_query(employee_id)))))


def check_no_gained_guests(db: Session, employee_id: int, had: set[int], owned_before: set[int]) -> None:
    """После правки брони батлером (внутри операции — предпросмотр совпадает с сохранением): ни
    один прежний проживающий, который не был своим, не стал своим (решение 9). Иначе, сдвинув даты
    чужого гостя на ночь своей строки «вся бронь / группа» или добавив ему вторую запись, батлер
    открыл бы себе его профиль. Новые родственники (правило состава) своими стать могут."""
    db.flush()
    if owned_among(db, employee_id, had) - owned_before:
        raise MineForbidden("Так чужой гость стал бы вашим: менять даты и записи гостей, которых "
                            "вы не ведёте, нельзя")


def _iso(v):
    return v.isoformat() if isinstance(v, dt.date) else v


def check_reservation_change(db: Session, before: dict, doc: dict) -> None:
    """Сравнить документ батлера с текущим: запертые поля, переезды, закрепления, главный гость;
    новый проживающий — родственник кого-то из прежних проживающих по семейному дереву (в том
    числе вычисленный, domain/kinship) или его прямая связь любого вида (§3) — иначе так можно
    было бы открыть себе профиль любого гостя."""
    def locked(d: dict, k: str):
        # пустая «оплата за» — категория брони
        return _iso(d.get(k) or d.get("category_id")) if k == "paid_category_id" else _iso(d.get(k))
    if any(locked(doc, k) != locked(before, k) for k in LOCKED):
        raise MineForbidden(MINE_TEXT)
    if [(_iso(m["move_date"]), m["category_id"]) for m in doc["moves"]] != \
            [(m["move_date"], m["category_id"]) for m in before["moves"]]:
        raise MineForbidden(MINE_TEXT)
    if doc.get("pins"):
        raise MineForbidden(MINE_TEXT)

    def mains(occ):
        return sorted((o["guest_id"], _iso(o["date_from"]), _iso(o["date_to"])) for o in occ if o["role"] == "main")
    if mains(doc["occupants"]) != mains(before["occupants"]):
        raise MineForbidden(MINE_TEXT)
    had = {o["guest_id"] for o in before["occupants"]}
    new = {o["guest_id"] for o in doc["occupants"]} - had
    if not new:
        return
    linked = set()
    for a, b in db.execute(select(GuestLink.guest_a_id, GuestLink.guest_b_id).where(
            (GuestLink.guest_a_id.in_(had) & GuestLink.guest_b_id.in_(new))
            | (GuestLink.guest_b_id.in_(had) & GuestLink.guest_a_id.in_(new)))):
        linked |= {a, b}
    rest = new - linked
    if rest and not rest <= family.relatives_among(db, had, rest):
        raise MineForbidden("Батлер добавляет только родственников и связанных с проживающими брони")


def check_link_change(db: Session, employee_id: int, link: GuestLink) -> None:
    """Удалить связь или отметить «бывших» батлер может, если хотя бы одна её сторона — свой гость."""
    if not any(owns_guest(db, employee_id, g) for g in (link.guest_a_id, link.guest_b_id)):
        raise MineForbidden("Это связь чужих гостей: вы не ведёте ни одного из них")


def check_guest_change(before: dict, data: dict) -> None:
    for k, v in data.items():
        if k in GUEST_FREE:
            continue
        old = before.get("phone") if k == "phone" else before.get(k)
        if k == "phone":
            from .guests import normalize_phone
            v = normalize_phone(v)
        if _iso(v) != _iso(old) and not (v in ("", None) and old in ("", None)):
            raise MineForbidden(MINE_TEXT)


# ── Экран «Мои гости» (часть 4 §5): сегодня, мой месяц, все мои гости ─────────────────────
# Бюджет SQL (§7): у каждого — постоянное число запросов; история батлера читается только
# пакетами (IN по своим), контекст покрытия — на день или период, а не на историю.

SOON_DAYS = 7               # особые даты и дни рождения — в ближайшие 7 дней
MAX_MONTH_DAYS = 62
GUESTS_PAGE = 50


def _soon(g: Guest, today: dt.date) -> list[dict]:
    """Особые даты и день рождения в ближайшие SOON_DAYS дней — ежегодные, датой ближайшего раза."""
    out = []
    marks = [(g.birth_date, "День рождения")] if g.birth_date else []
    for s in json.loads(g.special_dates_json or "[]"):
        try:
            marks.append((dt.date.fromisoformat(s.get("date") or ""), s.get("what") or ""))
        except (TypeError, ValueError, AttributeError):
            continue
    for d, what in marks:
        n = days_to_birthday(d, today)
        if n <= SOON_DAYS:
            out.append({"date": (today + dt.timedelta(days=n)).isoformat(), "what": what})
    return sorted(out, key=lambda x: x["date"])


def _led(ctx, employee_id: int, day: dt.date) -> dict[int, list[int]]:
    """Бронь → гости, которых батлер ведёт в ночь day (по разрешённому покрытию дня)."""
    out: dict[int, list[int]] = {}
    for (rid, g), emps in ctx.cover(day).by_guest.items():
        if employee_id in emps:
            out.setdefault(rid, []).append(g)
    return out


def mine_today(db: Session, employee_id: int) -> dict:
    """«Сегодня»: брони, где батлер ведёт кого-то в эту ночь, и гости, которых он вёл прошлой ночью
    и которые выезжают сегодня (departing — виден трансфер выезда). Объект — по фонду ночи, гости —
    те, кого ведёт он, логистика на сегодня и завтра (и без даты)."""
    today = local_date()
    yesterday = today - dt.timedelta(days=1)
    ctx = load_context(db, yesterday, today, None)
    # бронь → {гость: (запись «проживающий», выезжает сегодня)}
    led: dict[int, dict[int, tuple[Occupant, bool]]] = {}
    for rid, gids in _led(ctx, employee_id, today).items():
        occ = {o.guest_id: o for o in ctx.occ.get(rid, ()) if o.date_from <= today < o.date_to}
        led[rid] = {g: (occ[g], False) for g in gids if g in occ and g in ctx.guests}
    for rid, gids in _led(ctx, employee_id, yesterday).items():
        r = ctx.res[rid]
        for o in ctx.occ.get(rid, ()):
            if o.guest_id in gids and o.guest_id in ctx.guests and o.date_from <= yesterday < o.date_to \
                    and o.date_to == today and o.guest_id not in led.get(rid, {}):
                led.setdefault(rid, {})[o.guest_id] = (o, True)
        if r.check_out == today and not ctx.occ.get(rid):
            led.setdefault(rid, {})            # бронь без состава («гость брони») — тоже выезд
    logistics: dict[int, list] = {}
    if led:
        for lg in db.scalars(select(Logistics).where(
                Logistics.reservation_id.in_(list(led)),
                or_(Logistics.date.is_(None), Logistics.date.in_([today, today + dt.timedelta(days=1)])))
                .order_by(Logistics.date, Logistics.time)):
            logistics.setdefault(lg.reservation_id, []).append({"kind": lg.kind, "date": _iso(lg.date), "time": lg.time,
                                                                "description": lg.description})
    out = []
    for rid, by_guest in led.items():
        r = ctx.res[rid]
        guests = []
        for gid, (o, departing) in sorted(by_guest.items(), key=lambda x: (x[1][0].role != "main", x[1][0].id)):
            g = ctx.guests[gid]
            code = ctx.vip_codes.get(g.vip_code_id) if g.vip_code_id is not None else None
            guests.append({"guest_id": gid, "name": short_name(g), "special": bool(g.special),
                           "vip_code": code.code if code else "", "role": o.role,
                           "phone": format_phone(g.phone), "preferences": json.loads(g.preferences_json or "{}"),
                           "special_dates_soon": _soon(g, today), "departing": departing})
        departing = all(x["departing"] for x in guests) if guests else r.check_out == today
        night = yesterday if departing else today      # объект — ночи, в которую батлер ведёт гостей
        out.append({"reservation_id": rid, "number": r.number, "status": r.status,
                    "unit": ctx.unit_label(ctx.unit_of(rid, night)[0], night),
                    "check_in": _iso(r.check_in), "check_out": _iso(r.check_out), "guests": guests,
                    "departing": departing, "note": r.note,
                    "logistics": logistics.get(rid, [])})
    out.sort(key=lambda x: (natural_key(x["unit"]), x["reservation_id"]))
    return {"date": today.isoformat(), "reservations": out}


def mine_month(db: Session, employee_id: int, first: dt.date, last: dt.date, duty: DutyPort) -> dict:
    """«Мой месяц»: свои брони периода полосами по половинкам суток (как на шахматке) — строки по
    объектам (обозначение по фонду дня), «без объекта» внизу; нагрузка батлера по дням из одного
    контекста покрытия на период; дни отсутствия по Графику."""
    if last < first or (last - first).days + 1 > MAX_MONTH_DAYS:
        raise FundError(f"Период — не больше {MAX_MONTH_DAYS} дней")
    ctx = load_context(db, first, last, None)
    q, _ln, r = _my_line_res(employee_id)
    owned = set(db.scalars(q.with_only_columns(r.id).distinct()
                           .where(r.check_in <= last, r.check_out > first))) & set(ctx.res)
    lo, hi = pos(first, AM), pos(last, PM)
    rows: dict[int | None, dict] = {}
    for rid in sorted(owned, key=lambda x: (ctx.res[x].check_in, x)):
        res = ctx.res[rid]
        occ = ctx.occ.get(rid, [])
        mains = [o for o in occ if o.role == "main" and o.guest_id in ctx.guests]
        on_day = max(res.check_in, first)
        main = next((o for o in mains if o.date_from <= on_day < o.date_to), mains[0] if mains else None)
        special = any(ctx.guests[o.guest_id].special for o in occ if o.guest_id in ctx.guests)
        # полоса — соседние части одного сегмента с тем же объектом (граница версии фонда не видна)
        for (_seg, uid), run in groupby(ctx.segs[rid], key=lambda p, rid=rid: (p.seg_index, ctx.asg.get((rid, p.index)))):
            run = list(run)
            start, end = run[0].start_pos, run[-1].end_pos
            if end < lo or start > hi:
                continue
            row = rows.setdefault(uid, {"unit_id": uid, "label": ctx.unit_label(uid, dt.date.fromordinal(
                max(start, lo) // 2)), "bars": []})
            row["bars"].append({"reservation_id": rid, "start_pos": start, "end_pos": end, "status": res.status,
                                "main_guest": short_name(ctx.guests[main.guest_id]) if main else "",
                                "special": special})
    ordered = sorted((v for k, v in rows.items() if k is not None), key=lambda x: (natural_key(x["label"]), x["unit_id"]))
    if None in rows:
        ordered.append(rows[None])
    load = []
    for d in ctx.days():
        n = sum(len(gs) for gs in _led(ctx, employee_id, d).values())
        if not n:
            continue
        value = round(ctx.loads(d).get(employee_id, 0.0), 2)
        load.append({"day": d.isoformat(), "value": value, "guests": n,
                     "level": "over" if value > ctx.limit else "many" if n > 1 else "one"})
    got = duty.duty([employee_id], first, last)
    absences = [d.isoformat() for d in ctx.days() if (st := got.get((employee_id, d))) and st.code in ctx.codes]
    return {"days": [d.isoformat() for d in ctx.days()], "rows": ordered, "load": load, "limit": ctx.limit,
            "absences": absences}


def mine_guests(db: Session, employee_id: int, q: str = "", offset: int = 0, limit: int = GUESTS_PAGE,
                full: bool = False) -> dict:
    """«Все мои гости»: свои за всё время, поиск как подбор гостя (ниже полного уровня — по ФИО),
    по GUESTS_PAGE. Последний заезд и число проживаний — только начавшиеся (заезд не позже
    сегодня), следующий заезд — ближайший будущий; без отменённых и «не заехал»; одним запросом."""
    stmt = select(Guest).where(Guest.id.in_(_guest_ids_query(employee_id)))
    ts = text_search(q, full)
    if ts is not None:
        stmt = stmt.where(guest_search_column(full).contains(ts.needle, autoescape=True))
    total = db.scalar(stmt.with_only_columns(func.count(Guest.id)).order_by(None)) or 0
    page = list(db.scalars(stmt.order_by(Guest.last_name, Guest.first_name, Guest.id).offset(offset).limit(limit)))
    today = local_date()
    past: dict[int, set[int]] = {}
    last: dict[int, dt.date] = {}
    nxt: dict[int, dt.date] = {}
    if page:
        for gid, rid, a in db.execute(
                select(Occupant.guest_id, Occupant.reservation_id, Occupant.date_from)
                .join(Reservation, Reservation.id == Occupant.reservation_id)
                .where(Occupant.guest_id.in_([g.id for g in page]), Reservation.status.in_(allocation.OCCUPYING))):
            if a <= today:
                past.setdefault(gid, set()).add(rid)
                last[gid] = max(last.get(gid, a), a)
            else:
                nxt[gid] = min(nxt.get(gid, a), a)
    codes = code_texts(db) if any(g.vip_code_id for g in page) else {}
    rows = [{"guest_id": g.id, "name": full_name(g), "special": bool(g.special),
             "vip_code": codes.get(g.vip_code_id, ("", False))[0],
             "last_stay": _iso(last.get(g.id)), "next_stay": _iso(nxt.get(g.id)),
             "stays": len(past.get(g.id, ()))} for g in page]
    return {"rows": rows, "total": total}


def mine_guest_card(db: Session, employee_id: int, g: Guest) -> dict:
    """Карточка своего гостя: профиль целиком (как у «Профили гостей целиком») и история
    проживаний — кто его вёл, отрезками («вёл я» / имя другого батлера)."""
    return {**guest_dict(g), **guest_profile_extra(db, g), "links": links_of(db, g.id),
            "history": guest_led_history(db, g.id, employee_id)}
