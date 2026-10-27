"""Брони (§3.3, §4.7, §9): документ брони целиком — поля, переезды, проживающие со своими
датами, сопровождающие, логистика, закрепления; статусы с no-show; защита версией от
одновременной правки. Ничего не коммитит — commit в роутере."""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.time import local_date

from ..adapters.orm import (
    Assignment,
    Companion,
    Guest,
    Hold,
    Label,
    Logistics,
    Move,
    Occupant,
    Reservation,
    StayGroup,
)
from ..domain.halfday import PIECE_BASE, pieces, segments, validate_dates
from . import allocation
from .fund import FundError, changes
from .fund_versions import category_exists, fund_for, unit_exists, version_cuts
from .guests import reservation_search_text, searchable_codes, short_name, validate_fields

STATUS_TITLES = {"tentative": "предварительная", "confirmed": "подтверждена", "in_house": "заселён",
                 "checked_out": "выехал", "cancelled": "отменена", "no_show": "не заехал"}
TRANSITIONS = {
    "tentative": {"confirmed", "cancelled", "no_show"},
    "confirmed": {"tentative", "in_house", "cancelled", "no_show"},
    "in_house": {"checked_out", "confirmed"},
    "checked_out": {"in_house"},
    "cancelled": {"confirmed"},
    "no_show": {"confirmed"},
}
SCALARS = ("number", "check_in", "check_out", "early", "late", "category_id", "paid_by", "label_id",
           "customer", "purpose", "note", "declined_butler", "group_id", "external_id", "source")
COMPANION_KINDS = {"security", "driver", "nanny", "pet", "other"}
LOGISTICS_KINDS = {"flight", "transfer", "car"}


class ReservationError(FundError):
    """Ошибка операции с бронью."""


class ReservationConflict(ReservationError):
    """Бронь изменилась с момента открытия → 409."""

    def __init__(self, msg: str = "Бронь изменилась — обновите"):
        super().__init__(msg)


class ReservationInvalid(ReservationError):
    """Ошибка ввода → 422."""


def _d(v) -> str | None:
    return v.isoformat() if isinstance(v, dt.date) else v


def _nights(a: dt.date, b: dt.date):
    d = a
    while d < b:
        yield d
        d += dt.timedelta(days=1)


def _check_occupants(ci: dt.date, co: dt.date, occ: list[dict]) -> None:
    for o in occ:
        if not (ci <= o["date_from"] < o["date_to"] <= co):
            raise ReservationInvalid("Даты гостя вне дат брони")
        if o["role"] not in ("main", "guest"):
            raise ReservationInvalid("Роль гостя: главный или проживающий")
    if not occ:
        return                      # бронь без состава (например, из Fidelio без гостей) допустима
    for night in _nights(ci, co):
        mains = [o for o in occ if o["role"] == "main" and o["date_from"] <= night < o["date_to"]]
        if len(mains) != 1:
            word = "нет главного гостя" if not mains else "два главных гостя"
            raise ReservationInvalid(f"На {night.strftime('%d.%m')} {word}")


def _check_refs(db: Session, doc: dict) -> None:
    if not category_exists(db, doc["category_id"]):
        raise ReservationInvalid("Категория не найдена")
    for m in doc["moves"]:
        if not category_exists(db, m["category_id"]):
            raise ReservationInvalid("Категория переезда не найдена")
    if doc.get("label_id") is not None and db.get(Label, doc["label_id"]) is None:
        raise ReservationInvalid("Метка не найдена")
    if doc.get("group_id") is not None and db.get(StayGroup, doc["group_id"]) is None:
        raise ReservationInvalid("Группа совместного проживания не найдена")
    gids = {o["guest_id"] for o in doc["occupants"]}
    if gids and len(set(db.scalars(select(Guest.id).where(Guest.id.in_(gids))))) != len(gids):
        raise ReservationInvalid("Гость не найден")
    n_segments = len(doc["moves"]) + 1
    for seg, uid in (doc.get("pins") or {}).items():
        if not 0 <= int(seg) < n_segments:
            raise ReservationInvalid("Закрепление для несуществующего сегмента")
        if uid is not None and not unit_exists(db, uid):
            raise ReservationInvalid("Объект закрепления не найден")
    for c in doc["companions"]:
        if c["kind"] not in COMPANION_KINDS:
            raise ReservationInvalid("Неизвестный тип сопровождающего")
    for lg in doc["logistics"]:
        if lg["kind"] not in LOGISTICS_KINDS:
            raise ReservationInvalid("Неизвестный тип логистики")


def _moves_of(db: Session, rid: int) -> list[tuple[dt.date, int]]:
    return sorted((m.move_date, m.category_id)
                  for m in db.scalars(select(Move).where(Move.reservation_id == rid)))


def _group_others(db: Session, gid: int | None, rid: int | None) -> list[Reservation]:
    if gid is None:
        return []
    return list(db.scalars(select(Reservation).where(Reservation.group_id == gid,
                                                     Reservation.id != (rid or 0))))


def _check_group(db: Session, doc: dict, rid: int | None) -> None:
    """Переезды и категория группы общие (одна бронь объекта): правка одного члена
    переносится на остальных — даты переезда должны попадать в проживание каждого."""
    for other in _group_others(db, doc.get("group_id"), rid):
        if any(not other.check_in < m["move_date"] < other.check_out for m in doc["moves"]):
            raise ReservationInvalid(f"Переезд группы вне дат брони {other.number or other.id}")


def _sync_group(db: Session, r: Reservation, doc: dict) -> None:
    mine = sorted((m["move_date"], m["category_id"]) for m in doc["moves"])
    for other in _group_others(db, r.group_id, r.id):
        if other.category_id == r.category_id and _moves_of(db, other.id) == mine:
            continue
        other.category_id = r.category_id
        db.execute(delete(Move).where(Move.reservation_id == other.id))
        db.add_all(Move(reservation_id=other.id, move_date=d, category_id=c) for d, c in mine)
        other.version += 1
    db.flush()


def reservation_snapshot(db: Session, r: Reservation) -> dict:
    """Плоский снимок брони для журнала «было → стало» (§3.6)."""
    moves = _moves_of(db, r.id)
    # обозначение — на дату начала части сегмента (фонд меняется версиями с даты)
    starts = {p.index: p.start for p in pieces(segments(r.check_in, r.check_out, r.early, r.late, r.category_id,
                                                        moves), version_cuts(db))}
    fund = fund_for(db, r.check_in, r.check_out)
    units = [u.label if a.unit_id and (u := fund.unit(a.unit_id, starts.get(a.seg_index, r.check_in))) else None
             for a in db.scalars(select(Assignment).where(Assignment.reservation_id == r.id)
                                 .order_by(Assignment.seg_index))]
    occ = [[o.guest_id, _d(o.date_from), _d(o.date_to), o.role] for o in
           db.scalars(select(Occupant).where(Occupant.reservation_id == r.id).order_by(Occupant.id))]
    return {**{k: _d(getattr(r, k)) for k in SCALARS}, "status": r.status,
            "fields": json.loads(r.fields_json or "{}"),
            "moves": [[_d(d), c] for d, c in moves], "units": units, "occupants": occ}


def save_reservation(db: Session, doc: dict, rid: int | None,
                     expected_version: int | None) -> tuple[Reservation, dict]:
    """Создать или заменить документ брони. Возвращает бронь и снимок «до» (пустой для новой)."""
    if rid is None:
        r = Reservation(status=doc.get("status") or "confirmed", version=0)
        if r.status not in ("tentative", "confirmed"):
            raise ReservationInvalid("Новая бронь — предварительная или подтверждённая")
        before: dict = {}
    else:
        r = db.get(Reservation, rid)
        if r is None:
            raise ReservationInvalid("Бронь не найдена")
        if r.version != expected_version:
            raise ReservationConflict()
        before = reservation_snapshot(db, r)
    joining = doc.get("group_id") is not None and (rid is None or r.group_id != doc["group_id"])
    others = _group_others(db, doc.get("group_id"), rid)
    if joining and others:
        # новичок группы получает её переезды и категорию — а не переписывает их остальным
        doc = {**doc, "category_id": others[0].category_id,
               "moves": [{"move_date": d, "category_id": c} for d, c in _moves_of(db, others[0].id)]}
    errors = validate_dates(doc["check_in"], doc["check_out"], [m["move_date"] for m in doc["moves"]])
    if errors:
        raise ReservationInvalid(errors[0])
    _check_refs(db, doc)
    _check_occupants(doc["check_in"], doc["check_out"], doc["occupants"])
    _check_group(db, doc, rid)
    fields = validate_fields(db, "reservation", doc.get("fields") or {})

    for k in SCALARS:
        if k in doc:
            setattr(r, k, doc[k])
    r.fields_json = json.dumps(fields, ensure_ascii=False)
    r.search_text = reservation_search_text(r, searchable_codes(db, "reservation"))
    r.version += 1
    if rid is None:
        db.add(r)
    db.flush()
    _replace_children(db, r, doc)
    _sync_group(db, r, doc)
    _apply_pins(db, r, doc.get("pins"))
    allocation.run_allocation(db)
    return r, before


def _replace_children(db: Session, r: Reservation, doc: dict) -> None:
    db.execute(delete(Move).where(Move.reservation_id == r.id))
    db.add_all(Move(reservation_id=r.id, move_date=m["move_date"], category_id=m["category_id"])
               for m in doc["moves"])
    db.execute(delete(Companion).where(Companion.reservation_id == r.id))
    db.add_all(Companion(reservation_id=r.id, kind=c["kind"], description=c["description"])
               for c in doc["companions"])
    db.execute(delete(Logistics).where(Logistics.reservation_id == r.id))
    db.add_all(Logistics(reservation_id=r.id, kind=lg["kind"], date=lg.get("date"), time=lg.get("time", ""),
                         description=lg.get("description", "")) for lg in doc["logistics"])
    # проживающие — по id: история проживания и журнал опираются на устойчивые записи
    existing = {o.id: o for o in db.scalars(select(Occupant).where(Occupant.reservation_id == r.id))}
    keep = set()
    for o in doc["occupants"]:
        row = existing.get(o.get("id")) if o.get("id") else None
        if row is None:
            row = Occupant(reservation_id=r.id)
            db.add(row)
        row.guest_id, row.date_from, row.date_to, row.role = (o["guest_id"], o["date_from"],
                                                              o["date_to"], o["role"])
        if o.get("id") in existing:
            keep.add(o["id"])
    gone = [oid for oid in existing if oid not in keep]
    if gone:
        db.execute(delete(Occupant).where(Occupant.id.in_(gone)))
    db.flush()


def _apply_pins(db: Session, r: Reservation, pins: dict | None) -> None:
    """pins — сегмент → объект. Закрепление сегмента пишется всем его частям (строкам
    seg * PIECE_BASE + n); нет строк — первой части, остальные получит распределение.
    Закрепление у брони группы — закрепление всей группы: пишется всем её членам."""
    if pins is None:
        return
    rids = [r.id] + [o.id for o in _group_others(db, r.group_id, r.id)]
    rows: dict[tuple[int, int], list[Assignment]] = {}
    for a in db.scalars(select(Assignment).where(Assignment.reservation_id.in_(rids))):
        rows.setdefault((a.reservation_id, a.seg_index // PIECE_BASE), []).append(a)
    for rid in rids:
        for seg, uid in pins.items():
            parts = rows.get((rid, int(seg)), [])
            if uid is None:
                # «Авто» снимает только закрепление: объект замороженной части остаётся
                for a in parts:
                    a.pinned = False
                continue
            if not parts:
                parts = [Assignment(reservation_id=rid, seg_index=int(seg) * PIECE_BASE)]
                db.add(parts[0])
            for a in parts:
                a.unit_id, a.pinned = uid, True
    db.flush()


def set_status(db: Session, rid: int, status: str, expected_version: int,
               new_check_in: dt.date | None = None) -> tuple[Reservation, dict]:
    r = db.get(Reservation, rid)
    if r is None:
        raise ReservationInvalid("Бронь не найдена")
    if r.version != expected_version:
        raise ReservationConflict()
    if status not in STATUS_TITLES:
        raise ReservationInvalid("Неизвестный статус")
    if status not in TRANSITIONS[r.status]:
        raise ReservationInvalid(f"Нельзя перевести бронь из «{STATUS_TITLES[r.status]}» "
                                 f"в «{STATUS_TITLES[status]}»")
    if status == "no_show" and local_date() < r.check_in:
        raise ReservationInvalid("Отметить «не заехал» можно с даты заезда")
    before = reservation_snapshot(db, r)
    if r.status == "no_show" and status == "confirmed":
        # гость приехал позже: новая дата заезда, состав сдвигается вместе с ней (§4.7)
        if new_check_in is None:
            raise ReservationInvalid("Укажите новую дату заезда")
        if new_check_in < r.check_in:
            raise ReservationInvalid("Новая дата заезда — не раньше прежней")
        errors = validate_dates(new_check_in, r.check_out, [d for d, _ in _moves_of(db, r.id)])
        if errors:
            raise ReservationInvalid(errors[0])
        kept = []
        for o in db.scalars(select(Occupant).where(Occupant.reservation_id == r.id)):
            if o.date_to <= new_check_in:
                db.delete(o)                     # у гостя не осталось ночей
                continue
            o.date_from = max(o.date_from, new_check_in)
            kept.append({"date_from": o.date_from, "date_to": o.date_to, "role": o.role})
        _check_occupants(new_check_in, r.check_out, kept)
        r.check_in = new_check_in
    r.status = status
    r.version += 1
    db.flush()
    allocation.run_allocation(db)
    return r, before


def reservation_dict(db: Session, r: Reservation, state: allocation.AllocationState | None = None) -> dict:
    """Документ брони для формы правки (уровень «полный», только stays.edit)."""
    moves = _moves_of(db, r.id)
    segs = segments(r.check_in, r.check_out, r.early, r.late, r.category_id, moves)
    # сегмент формы — объект его первой части; закреплён, если закреплена любая часть
    asg: dict[int, Assignment] = {}
    pinned: set[int] = set()
    for a in db.scalars(select(Assignment).where(Assignment.reservation_id == r.id)):
        if a.seg_index % PIECE_BASE == 0:
            asg[a.seg_index // PIECE_BASE] = a
        if a.pinned:
            pinned.add(a.seg_index // PIECE_BASE)
    occ = list(db.scalars(select(Occupant).where(Occupant.reservation_id == r.id)
                          .order_by(Occupant.date_from, Occupant.id)))
    names = {g.id: g for g in db.scalars(select(Guest).where(Guest.id.in_({o.guest_id for o in occ})))} if occ else {}
    return {
        "id": r.id, "version": r.version, "status": r.status, "status_title": STATUS_TITLES[r.status],
        **{k: _d(getattr(r, k)) for k in SCALARS}, "fields": json.loads(r.fields_json or "{}"),
        "moves": [{"move_date": _d(d), "category_id": c} for d, c in moves],
        "segments": [{"index": s.index, "category_id": s.category_id, "start": _d(s.start), "end": _d(s.end),
                      "unit_id": asg[s.index].unit_id if s.index in asg else None,
                      "pinned": s.index in pinned} for s in segs],
        "occupants": [{"id": o.id, "guest_id": o.guest_id, "date_from": _d(o.date_from),
                       "date_to": _d(o.date_to), "role": o.role,
                       "name": short_name(names[o.guest_id]) if o.guest_id in names else "",
                       "level": names[o.guest_id].level if o.guest_id in names else "regular"} for o in occ],
        "companions": [{"kind": c.kind, "description": c.description} for c in
                       db.scalars(select(Companion).where(Companion.reservation_id == r.id).order_by(Companion.id))],
        "logistics": [{"kind": lg.kind, "date": _d(lg.date), "time": lg.time, "description": lg.description}
                      for lg in db.scalars(select(Logistics).where(Logistics.reservation_id == r.id)
                                           .order_by(Logistics.date, Logistics.id))],
        "warnings": allocation.warnings_for(state or allocation.current_state(db), r.id),
    }


def diff_of(before: dict, db: Session, r: Reservation) -> dict:
    return changes(before, reservation_snapshot(db, r))


def save_hold(db: Session, data: dict, hid: int | None) -> tuple[Hold, dict]:
    if not unit_exists(db, data["unit_id"]):
        raise ReservationInvalid("Объект не найден")
    if data["end"] < data["start"]:
        raise ReservationInvalid("Конец блока раньше начала")
    if data["kind"] not in ("block", "ooo"):
        raise ReservationInvalid("Тип: блок или OOO")
    if hid is None:
        h = Hold()
        db.add(h)
        before: dict = {}
    else:
        h = db.get(Hold, hid)
        if h is None:
            raise ReservationInvalid("Блок не найден")
        before = hold_dict(h)
    for k in ("unit_id", "start", "end", "kind", "title"):
        setattr(h, k, data[k])
    db.flush()
    allocation.run_allocation(db)
    return h, before


def delete_hold(db: Session, hid: int) -> dict:
    h = db.get(Hold, hid)
    if h is None:
        raise ReservationInvalid("Блок не найден")
    before = hold_dict(h)
    db.delete(h)
    db.flush()
    allocation.run_allocation(db)
    return before


def hold_dict(h: Hold) -> dict:
    return {"id": h.id, "unit_id": h.unit_id, "start": _d(h.start), "end": _d(h.end), "kind": h.kind,
            "title": h.title}


def doc_of(db: Session, r: Reservation, **changes) -> dict:
    """Документ брони как его прислала бы форма — для операций поверх save_reservation."""
    d = reservation_dict(db, r)
    day = dt.date.fromisoformat
    return {**{k: d[k] for k in SCALARS}, "check_in": day(d["check_in"]), "check_out": day(d["check_out"]),
            "fields": d["fields"], "pins": None,
            "moves": [{"move_date": day(m["move_date"]), "category_id": m["category_id"]} for m in d["moves"]],
            "occupants": [{"id": o["id"], "guest_id": o["guest_id"], "role": o["role"],
                           "date_from": day(o["date_from"]), "date_to": day(o["date_to"])} for o in d["occupants"]],
            "companions": d["companions"],
            "logistics": [{**lg, "date": day(lg["date"]) if lg["date"] else None} for lg in d["logistics"]],
            **changes}


def cohabit_candidates(db: Session, rid: int) -> list[dict]:
    """С кем бронь может проживать вместе (§3.3): та же категория, даты пересекаются."""
    r = db.get(Reservation, rid)
    if r is None:
        raise ReservationInvalid("Бронь не найдена")
    rows = list(db.scalars(select(Reservation).where(
        Reservation.id != rid, Reservation.category_id == r.category_id,
        Reservation.status.in_(allocation.OCCUPYING), Reservation.check_in < r.check_out,
        Reservation.check_out > r.check_in).order_by(Reservation.check_in, Reservation.id)))
    mains = {}
    if rows:
        for o in db.scalars(select(Occupant).where(Occupant.reservation_id.in_([x.id for x in rows]),
                                                  Occupant.role == "main").order_by(Occupant.date_from)):
            mains.setdefault(o.reservation_id, o.guest_id)
    names = {g.id: short_name(g) for g in db.scalars(select(Guest).where(Guest.id.in_(set(mains.values()))))} \
        if mains else {}
    return [{"reservation_id": x.id, "number": x.number, "check_in": _d(x.check_in), "check_out": _d(x.check_out),
             "group_id": x.group_id, "main_guest": names.get(mains.get(x.id), "")} for x in rows]


def join_group(db: Session, rids: list[int]) -> tuple[int, list[tuple[Reservation, dict]]]:
    """Совместное проживание одной операцией: брони встают в одну группу (существующую у
    кого-то из них или новую) — тот же путь, что правка брони, с проверками и переездами группы."""
    res = [db.get(Reservation, rid) for rid in dict.fromkeys(rids)]
    if len(res) < 2 or any(r is None for r in res):
        raise ReservationInvalid("Укажите хотя бы две брони")
    if any(r.status not in allocation.OCCUPYING for r in res):
        raise ReservationInvalid("Отменённую бронь и «не заехал» в группу не включить")
    if len({r.category_id for r in res}) > 1:
        raise ReservationInvalid("Совместное проживание — брони одной категории")
    gid = next((r.group_id for r in res if r.group_id is not None), None)
    if gid is None:
        g = StayGroup(title="")
        db.add(g)
        db.flush()
        gid = g.id
    saved = []
    for r in res:
        if r.group_id != gid:
            saved.append(save_reservation(db, doc_of(db, r, group_id=gid), r.id, r.version))
    return gid, saved


def leave_group(db: Session, rid: int) -> tuple[Reservation, dict, int | None]:
    r = db.get(Reservation, rid)
    if r is None or r.group_id is None:
        raise ReservationInvalid("Бронь не в группе совместного проживания")
    old = r.group_id
    saved, before = save_reservation(db, doc_of(db, r, group_id=None), r.id, r.version)
    return saved, before, old
