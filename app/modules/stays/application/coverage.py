"""Покрытие батлерами (§4.2, §4.5, §5): шаблоны, правка по дням, снятие строк, когда гостей
уже нет, подбор кандидатов и подмена, «добавить смену в График». Ничего не коммитит.

Строки покрытия и их гости удаляются кодом: на SQLite внешние ключи не проверяются, каскаду
доверять нельзя (ревью этапа 1)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.timesheet.application import schedule_view
from app.modules.timesheet.application.catalog import ShiftType
from app.modules.timesheet.application.engine_common import engine_ports
from app.modules.timesheet.application.errors import ScheduleInputError
from app.modules.timesheet.application.roster import roster

from ..adapters.orm import CoverageGuest, CoverageLine, Escort, Occupant, Reservation, StayGroup
from ..domain.candidates import rank_candidates
from ..domain.coverage import fill_template, resolve_day
from ..ports.duty import DutyPort
from . import allocation
from .context import load_context, nights
from .reservations import ReservationInvalid


class CoverageForbidden(ReservationInvalid):
    """Нет нужного права → 403."""


@dataclass(frozen=True)
class Scope:
    reservation_id: int | None
    group_id: int | None
    guest_ids: frozenset[int] = frozenset()


def _members(db: Session, scope: Scope) -> list[Reservation]:
    if scope.reservation_id is not None:
        r = db.get(Reservation, scope.reservation_id)
        return [r] if r is not None and r.status in allocation.OCCUPYING else []
    return list(db.scalars(select(Reservation).where(Reservation.group_id == scope.group_id,
                                                     Reservation.status.in_(allocation.OCCUPYING))))


def validate_scope(db: Session, scope: Scope) -> list[Reservation]:
    if (scope.reservation_id is None) == (scope.group_id is None):
        raise ReservationInvalid("Укажите бронь или группу совместного проживания")
    if scope.reservation_id is not None and db.get(Reservation, scope.reservation_id) is None:
        raise ReservationInvalid("Бронь не найдена")
    if scope.group_id is not None and db.get(StayGroup, scope.group_id) is None:
        raise ReservationInvalid("Группа совместного проживания не найдена")
    members = _members(db, scope)
    if not members:
        raise ReservationInvalid("Бронь отменена или гость не заехал — назначать некого")
    if scope.guest_ids:
        known = set(db.scalars(select(Occupant.guest_id).where(Occupant.reservation_id.in_([r.id for r in members]))))
        if not scope.guest_ids <= known:
            raise ReservationInvalid("Гость не из этой брони")
    return members


def scope_nights(db: Session, scope: Scope, members: list[Reservation]) -> set[dt.date]:
    out: set[dt.date] = set()
    occ = list(db.scalars(select(Occupant).where(Occupant.reservation_id.in_([r.id for r in members]))))
    for r in members:
        for d in nights(r.check_in, r.check_out):
            if not scope.guest_ids or any(o.reservation_id == r.id and o.guest_id in scope.guest_ids
                                          and o.date_from <= d < o.date_to for o in occ):
                out.add(d)
    return out


def _same_scope(db: Session, scope: Scope, days) -> list[CoverageLine]:
    q = select(CoverageLine).where(CoverageLine.day.in_(list(days)))
    q = q.where(CoverageLine.reservation_id == scope.reservation_id) if scope.reservation_id is not None \
        else q.where(CoverageLine.group_id == scope.group_id)
    rows = list(db.scalars(q))
    if not rows:
        return []
    picked: dict[int, set[int]] = {r.id: set() for r in rows}
    for cg in db.scalars(select(CoverageGuest).where(CoverageGuest.coverage_id.in_(list(picked)))):
        picked[cg.coverage_id].add(cg.guest_id)
    return [r for r in rows if picked[r.id] == set(scope.guest_ids)]


def delete_lines(db: Session, ids: list[int]) -> None:
    if ids:
        db.execute(delete(CoverageGuest).where(CoverageGuest.coverage_id.in_(ids)))
        db.execute(delete(CoverageLine).where(CoverageLine.id.in_(ids)))
        db.flush()


def _add_line(db: Session, scope: Scope, day: dt.date, employee_id: int, source: str,
              overnight: bool = False, comment: str = "") -> CoverageLine:
    row = CoverageLine(day=day, employee_id=employee_id, reservation_id=scope.reservation_id,
                       group_id=scope.group_id, source=source, overnight=overnight, comment=comment[:255])
    db.add(row)
    db.flush()
    db.add_all(CoverageGuest(coverage_id=row.id, guest_id=g) for g in sorted(scope.guest_ids))
    db.flush()
    return row


def _check_escorts(db: Session, butlers: list[int]) -> None:
    active = set(db.scalars(select(Escort.employee_id).where(Escort.active.is_(True))))
    if not set(butlers) <= active:
        raise ReservationInvalid("Батлер не в списке «Сопровождают гостей»")


def apply_template(db: Session, scope: Scope, kind: str, butlers: list[int], first: dt.date,
                   last: dt.date, replace: bool, duty: DutyPort) -> list[tuple[dt.date, int]]:
    if kind not in ("pair", "single") or len(butlers) != (2 if kind == "pair" else 1):
        raise ReservationInvalid("Шаблон «пара посменно» — два батлера, «один на весь срок» — один")
    if last < first:
        raise ReservationInvalid("Конец периода раньше начала")
    _check_escorts(db, butlers)
    members = validate_scope(db, scope)
    days = sorted(d for d in scope_nights(db, scope, members) if first <= d <= last)
    if replace:
        delete_lines(db, [r.id for r in _same_scope(db, scope, days)])
    busy = _covered_days(db, members, scope, days)       # уже покрыты любой строкой, в т. ч. группы
    plan = fill_template(kind, days, tuple(butlers), duty.duty(butlers, first, last), busy)
    for d, e in plan:
        _add_line(db, scope, d, e, "template")
    return plan


def set_day(db: Session, scope: Scope, day: dt.date, employee_id: int | None, overnight: bool,
            comment: str) -> CoverageLine | None:
    members = validate_scope(db, scope)
    if day not in scope_nights(db, scope, members):
        raise ReservationInvalid("В этот день гостей брони нет")
    if employee_id is not None:
        _check_escorts(db, [employee_id])
    delete_lines(db, [r.id for r in _same_scope(db, scope, [day])])
    if not employee_id:
        return None
    row = _add_line(db, scope, day, employee_id, "manual", overnight, comment)
    ctx = load_context(db, day, day, None)
    _stays, wanted = _scope_stays(ctx, members, scope, day)
    if any(len(ctx.cover(day).by_guest.get(k, ())) > 1 for k in wanted):
        raise ReservationInvalid("Гостей в этот день уже ведёт другая строка — измените её")
    return row


def set_days(db: Session, scope: Scope, days: list[tuple[dt.date, int | None]]) -> int:
    """Правка по дням одной операцией (форма «вручную»): батлер на день или «нет»."""
    for day, employee_id in days:
        set_day(db, scope, day, employee_id, False, "")
    return len(days)


def delete_line(db: Session, line_id: int) -> CoverageLine:
    row = db.get(CoverageLine, line_id)
    if row is None:
        raise ReservationInvalid("Строка покрытия не найдена")
    delete_lines(db, [line_id])
    return row


def cleanup_lines(db: Session, reservation_id: int, old_group_id: int | None = None) -> list[dict]:
    """Снять строки на дни, когда гостей брони уже нет (даты, отмена, no-show, состав, §4.2);
    строки группы — и нынешней, и прежней, если бронь из неё ушла."""
    r = db.get(Reservation, reservation_id)
    if r is None:
        return []
    occupying = r.status in allocation.OCCUPYING
    occ = list(db.scalars(select(Occupant).where(Occupant.reservation_id == r.id))) if occupying else []
    rows = list(db.scalars(select(CoverageLine).where(CoverageLine.reservation_id == r.id)))
    picked: dict[int, list[CoverageGuest]] = {x.id: [] for x in rows}
    if rows:
        for cg in db.scalars(select(CoverageGuest).where(CoverageGuest.coverage_id.in_(list(picked)))):
            picked[cg.coverage_id].append(cg)
    removed, drop = [], []
    for ln in rows:
        alive = occupying and r.check_in <= ln.day < r.check_out
        present = {o.guest_id for o in occ if o.date_from <= ln.day < o.date_to}
        gone = [cg for cg in picked[ln.id] if cg.guest_id not in present]
        if alive and picked[ln.id] and len(gone) < len(picked[ln.id]):
            for cg in gone:
                db.delete(cg)
            continue
        if alive and not picked[ln.id]:
            continue
        drop.append(ln.id)
        removed.append({"day": ln.day.isoformat(), "employee_id": ln.employee_id})
    for gid in {g for g in (r.group_id, old_group_id) if g is not None}:
        removed += _cleanup_group(db, gid, drop)
    delete_lines(db, drop)
    return removed


def _cleanup_group(db: Session, gid: int, drop: list[int]) -> list[dict]:
    """Строки группы: дни, когда в ней никто не ночует, снимаются; явные гости строки
    обрезаются до тех, кто в этот день живёт в группе."""
    members = _members(db, Scope(None, gid))
    occ = list(db.scalars(select(Occupant).where(Occupant.reservation_id.in_([m.id for m in members])))) if members else []
    rows = list(db.scalars(select(CoverageLine).where(CoverageLine.group_id == gid)))
    picked: dict[int, list[CoverageGuest]] = {x.id: [] for x in rows}
    if rows:
        for cg in db.scalars(select(CoverageGuest).where(CoverageGuest.coverage_id.in_(list(picked)))):
            picked[cg.coverage_id].append(cg)
    removed = []
    for ln in rows:
        alive = any(m.check_in <= ln.day < m.check_out for m in members)
        present = {o.guest_id for o in occ if o.date_from <= ln.day < o.date_to}
        gone = [cg for cg in picked[ln.id] if cg.guest_id not in present]
        if alive and len(gone) < len(picked[ln.id]):
            for cg in gone:
                db.delete(cg)
            continue
        if alive and not picked[ln.id]:
            continue
        drop.append(ln.id)
        removed.append({"day": ln.day.isoformat(), "employee_id": ln.employee_id, "group_id": gid})
    return removed


def _scope_stays(ctx, members: list[Reservation], scope: Scope, day: dt.date):
    rids = {m.id for m in members}
    stays = [s for s in ctx.stays_on(day) if s.reservation_id in rids]
    wanted = {(s.reservation_id, g) for s in stays for g in s.guests if not scope.guest_ids or g in scope.guest_ids}
    return stays, wanted


def _targets_scope(ln, scope: Scope) -> bool:
    return (scope.reservation_id is not None and ln.reservation_id == scope.reservation_id) or \
        (scope.group_id is not None and ln.group_id == scope.group_id)


def _covered_days(db: Session, members: list[Reservation], scope: Scope, days: list[dt.date]) -> set[dt.date]:
    """Дни, которые шаблон не трогает (§4.2 «только пустые дни»):
    * область с выбранными гостями — их уже ведут явной строкой («вся бронь» не в счёт:
      явный выбор сильнее, так и делят гостей между батлерами);
    * область «целиком» — у всех гостей есть батлер, или хоть одного уже ведёт строка
      «целиком» другой области (иначе у него было бы два батлера; остальные — видимая дыра)."""
    if not days:
        return set()
    ctx = load_context(db, min(days), max(days), None)
    out = set()
    for d in days:
        stays, wanted = _scope_stays(ctx, members, scope, d)
        if not wanted:
            continue
        lines = ctx.lines_on(d)
        if scope.guest_ids:
            if wanted <= set(resolve_day(stays, [ln for ln in lines if ln.guest_ids]).by_guest):
                out.add(d)
            continue
        whole_other = [ln for ln in lines if not ln.guest_ids and not _targets_scope(ln, scope)]
        if wanted <= set(ctx.cover(d).by_guest) or wanted & set(resolve_day(stays, whole_other).by_guest):
            out.add(d)
    return out


def rank_in_ctx(ctx, day: dt.date, stays: list, guest_ids: set[int], known) -> list[dict]:
    """Кандидаты из готового контекста дня (одна загрузка на весь экран)."""
    by_res = {s.reservation_id: s for s in ctx.stays_on(day)}
    places: dict[int, set] = {}
    for (rid, _g), emps in ctx.cover(day).by_guest.items():
        for e in emps:
            places.setdefault(e, set()).update({("unit", by_res[rid].unit_id), ("path", by_res[rid].group_path)})
    bonus = sum((ctx.vvip_bonus if s.guests.get(g) == "vvip" else ctx.vip_bonus if s.guests.get(g) == "vip" else 0)
                for s in stays for g in s.guests if g in guest_ids)
    got = rank_candidates(day, guest_ids, stays[0].unit_id, stays[0].group_path, ctx.escorts, ctx.duty,
                          ctx.loads(day), stays[0].weight + bonus, ctx.limit, known, places, ctx.codes)
    return [{"employee_id": c.employee_id, "name": ctx.name(c.employee_id), "knows_guest": c.knows_guest,
             "same_place": c.same_place, "load_after": round(c.load_after, 2), "note": c.note} for c in got]


def candidates(db: Session, day: dt.date, scope: Scope, duty: DutyPort) -> list[dict]:
    members = validate_scope(db, scope)
    ctx = load_context(db, day, day, duty)
    stays, _wanted = _scope_stays(ctx, members, scope, day)
    if not stays:
        raise ReservationInvalid("В этот день гостей брони нет")
    guest_ids = set(scope.guest_ids) or {g for s in stays for g in s.guests}
    return rank_in_ctx(ctx, day, stays, guest_ids, _known(db, guest_ids, day))


def _known(db: Session, guest_ids: set[int], before: dt.date) -> dict[int, set[int]]:
    """Кто вёл этих гостей раньше (§4.5 «знает гостя»): строки покрытия их прошлых броней."""
    occ = list(db.scalars(select(Occupant).where(Occupant.guest_id.in_(guest_ids))))
    if not occ:
        return {}
    res = {r.id: r for r in db.scalars(select(Reservation).where(Reservation.id.in_({o.reservation_id for o in occ})))}
    groups = {r.group_id for r in res.values() if r.group_id is not None}
    q = select(CoverageLine).where(CoverageLine.day < before)
    rows = list(db.scalars(q.where(CoverageLine.reservation_id.in_(list(res))))) + (
        list(db.scalars(q.where(CoverageLine.group_id.in_(groups)))) if groups else [])
    picked: dict[int, set[int]] = {r.id: set() for r in rows}
    if rows:
        for cg in db.scalars(select(CoverageGuest).where(CoverageGuest.coverage_id.in_(list(picked)))):
            picked[cg.coverage_id].add(cg.guest_id)
    out: dict[int, set[int]] = {}
    for ln in rows:
        for o in occ:
            r = res[o.reservation_id]
            targets = ln.reservation_id == r.id or (ln.group_id is not None and ln.group_id == r.group_id)
            if targets and o.date_from <= ln.day < o.date_to and (not picked[ln.id] or o.guest_id in picked[ln.id]):
                out.setdefault(ln.employee_id, set()).add(o.guest_id)
    return out


def replacement_list(db: Session, first: dt.date, last: dt.date, duty: DutyPort) -> list[dict]:
    """«Нужна подмена» на диапазон (§4.5): один контекст, история «знает гостя» — одним
    пакетом до начала диапазона; бронь группы — одна запись на группу."""
    ctx = load_context(db, first, last, duty)
    all_guests = {o.guest_id for os in ctx.occ.values() for o in os}
    known = _known(db, all_guests, first) if all_guests else {}
    out, seen = [], set()
    for d in ctx.days():
        for w in ctx.warnings(d):
            if w.kind != "need_replacement":
                continue
            r = ctx.res[w.reservation_id]
            scope_key = ("g", r.group_id) if r.group_id is not None else ("r", r.id)
            if (d, w.employee_id, scope_key) in seen:
                continue
            seen.add((d, w.employee_id, scope_key))
            stays = [s for s in ctx.stays_on(d) if s.reservation_id == r.id
                     or (r.group_id is not None and s.group_id == r.group_id)]
            guest_ids = {g for s in stays for g in s.guests}
            out.append({"day": d.isoformat(), "employee_id": w.employee_id, "employee": ctx.name(w.employee_id),
                        "reservation_id": r.id, "group_id": r.group_id, "number": r.number, "code": w.value,
                        "unit": ctx.unit_label(w.unit_id, d), "candidates": rank_in_ctx(ctx, d, stays, guest_ids, known)})
    return out


def add_shift(db: Session, perms: set[str], employee_id: int, day: dt.date, shift_type_id: int,
              principal) -> list:
    """«Добавить смену в График» (§5): ручная смена Графика через его же прикладной слой;
    Табель не меняется. Нужны stays.assign и право на правку Графика."""
    if "schedule.edit" not in perms:
        raise CoverageForbidden("Нужно право на правку Графика")
    kind = db.get(ShiftType, shift_type_id)
    if kind is None or kind.kind != "work":
        raise ReservationInvalid("Смена словаря не найдена")
    ports = engine_ports(db, principal)
    current = roster([employee_id], day, day, ports).get((employee_id, day))
    if current is not None and current.on_shift:
        raise ReservationInvalid("У сотрудника уже есть смена в этот день")
    try:
        return schedule_view.add_preset_shift(str(employee_id), day, kind, ports)
    except ScheduleInputError as e:
        raise ReservationInvalid(str(e)) from e
