"""График работы: сетка «ФИО × дни» с блоками Смена 1 / Смена 2 / Пятидневка / Другие смены,
переходы между сменами, периоды работы (приём → увольнение → повторный приём),
вид «Факт» (интервалы работы по отметкам), частичное отсутствие («отпросился с 14:00 до 16:00»),
назначение отсутствия на период ЛЮБОЙ длины (через границы месяцев),
продолжение цикла в следующий месяц, обнуление месяца, печать/экспорт сетки в Excel."""
from __future__ import annotations

import datetime as dt
import io
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal, audit, current_principal, require_manager
from ..base_schedule import BlockIndex, base_shift, load_base_config, parse_pattern, validate_pattern
from ..db import get_db
from ..deps import WD_SHORT, month_name, now_local
from ..doublepay import SCOPE_TITLES, calendar_map
from ..employment import employed_on, ensure_periods, is_employed, periods_of, ranges_from_periods
from ..factview import build_fact_map
from ..groups import group_index, normalize_group, sorted_groups
from ..models import BlockAssignment, Employee, EmploymentPeriod, ScheduleEntry, ShiftType, TimesheetRow, utcnow
from ..names import suggest_genitive
from ..schedule_patterns import pattern_days, pattern_list
from ..shiftrev import ShiftCatalog, ShiftView
from ..timesheet import entry_shift, gap_hours, load_rules, recalc_day, recalc_range, shift_window

router = APIRouter(prefix="/api/schedule", tags=["schedule"])

OUT_OF_BLOCK_COLOR = "#d8d3e8"     # «чужие» дни при переходе между сменами
WORKED_OFF_COLOR = "#7c3aed"       # работа в выходной — ячейка другого цвета
INACTIVE_COLOR = "#eceff4"         # дни вне периодов работы (уволен / ещё не принят)

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    first = dt.date(year, month, 1)
    nxt = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)
    return first, nxt - dt.timedelta(days=1)


def _shift_brief(s) -> Optional[dict]:
    """Краткое описание смены (или её исторического снимка) для интерфейса."""
    if s is None:
        return None
    if isinstance(s, ShiftView):
        return s.brief()
    return ShiftView(s).brief()


def _partial_brief(entry: Optional[ScheduleEntry]) -> Optional[dict]:
    """Согласованное частичное отсутствие в ячейке: «отпросился с 14:00 до 16:00»."""
    if entry is None or not (entry.from_time and entry.until_time):
        return None
    return {
        "from_time": entry.from_time, "until_time": entry.until_time,
        "hours": gap_hours(entry, entry.date),
        "reason": _shift_brief(entry.partial_shift),
    }


def _block_active(db: Session, emp_id: int, date: dt.date) -> bool:
    """День принадлежит активному блоку сотрудника (или блоков ещё нет — старая база)."""
    assigns = db.scalars(select(BlockAssignment).where(BlockAssignment.employee_id == emp_id)).all()
    if not assigns:
        return True
    return any(a.start_date <= date and (a.end_date is None or a.end_date >= date) for a in assigns)


def _pattern_label(raw: str) -> str:
    pat = parse_pattern(raw)
    if not pat:
        return ""
    try:
        return validate_pattern(pat)
    except ValueError:
        return ""


def _strip_to_plan(payload: dict) -> dict:
    """График для сотрудника (роль «батлер»): только план смен, без факта и начислений.

    Убираем всё, что относится к учёту и деньгам — интервалы по отметкам, часы,
    переработки, банк, причины отсутствий. Остаётся сетка «кто когда работает»,
    которую сотрудник может смотреть и печатать, но не редактировать."""
    for row in payload["rows"]:
        emp = row["employee"]
        emp.pop("balance_hours", None)
        row["totals"] = {"planned_hours": row["totals"]["planned_hours"],
                         "work_days": row["totals"]["work_days"], "fact_hours": 0.0}
        for cell in row["cells"].values():
            cell["fact"] = None
            cell["partial"] = None
            cell["note"] = ""
            cell["fact_hours"] = 0.0
            cell["worked_off"] = False
            cell.pop("punch_in_override", None)
            cell.pop("punch_out_override", None)
    return payload


@router.get("")
def get_grid(year: int, month: int, principal: Principal = Depends(current_principal),
             db: Session = Depends(get_db)):
    """Сетка графика на месяц: блоки смен, строки сотрудников (переходы, периоды работы),
    план-часы и «факт» (интервалы работы по отметкам) для каждого дня.

    Доступ: менеджерам — полностью; сотрудникам — только план (без факта и начислений).
    Править сетку могут лишь менеджеры (см. set_cell/set_bulk: require_manager)."""
    if not (1 <= month <= 12):
        raise HTTPException(status_code=422, detail="month должен быть 1..12")
    first, last = _month_bounds(year, month)
    days = [(first + dt.timedelta(days=i)) for i in range((last - first).days + 1)]

    # в сетке видны работающие сейчас И те, у кого в этом месяце есть период работы
    # (уволился в середине месяца, принят обратно) — история не должна пропадать
    candidates = db.scalars(select(Employee).where(Employee.deleted_at.is_(None))).all()
    all_periods = db.scalars(select(EmploymentPeriod).where(
        EmploymentPeriod.employee_id.in_([e.id for e in candidates]))).all() if candidates else []
    per_emp_periods: dict[int, list] = {}
    for p in all_periods:
        per_emp_periods.setdefault(p.employee_id, []).append(p)

    def _visible(emp: Employee) -> bool:
        if emp.active:
            return True
        recs = per_emp_periods.get(emp.id)
        if not recs:
            return bool(emp.dismissed_at and first <= emp.dismissed_at <= last)
        return any(p.start_date <= last and (p.end_date is None or p.end_date >= first) for p in recs)

    employees = [e for e in candidates if _visible(e)]
    employees.sort(key=lambda e: (group_index(normalize_group(e.schedule_group)), e.full_name))
    emp_ids = [e.id for e in employees]

    entries = db.scalars(select(ScheduleEntry).where(
        ScheduleEntry.date >= first, ScheduleEntry.date <= last,
        ScheduleEntry.employee_id.in_(emp_ids))).all() if emp_ids else []
    emap = {(e.employee_id, e.date): e for e in entries}

    ts_rows = db.scalars(select(TimesheetRow).where(
        TimesheetRow.date >= first, TimesheetRow.date <= last,
        TimesheetRow.employee_id.in_(emp_ids))).all() if emp_ids else []
    fmap = {(t.employee_id, t.date): t for t in ts_rows}
    fact_map = build_fact_map(db, emp_ids, first, last)
    base_cfg = load_base_config(db)

    blocks = db.scalars(select(BlockAssignment).where(
        BlockAssignment.employee_id.in_(emp_ids),
        BlockAssignment.start_date <= last,
    )).all() if emp_ids else []
    bmap: dict[int, list[dict]] = {}
    for b in blocks:
        if b.end_date and b.end_date < first:
            continue
        bmap.setdefault(b.employee_id, []).append(b)
    # одна строка на группу: периоды группы списком ranges + подпись индивидуального шаблона
    grouped: dict[int, list[dict]] = {}
    for emp_id, recs in bmap.items():
        per_group: dict[str, list[dict]] = {}
        labels: dict[str, str] = {}
        for b in recs:
            g = normalize_group(b.group)
            per_group.setdefault(g, []).append(
                {"start": b.start_date.isoformat(),
                 "end": b.end_date.isoformat() if b.end_date else None})
            lbl = _pattern_label(b.pattern_json)
            if lbl:
                labels[g] = lbl
        grouped[emp_id] = [
            {"group": g, "start": min(r["start"] for r in rs),
             "end": next((r["end"] for r in rs if r["end"] is None), None)
             or max((r["end"] for r in rs if r["end"]), default=None),
             "ranges": rs, "pattern_label": labels.get(g, "")}
            for g, rs in per_group.items()
        ]

    today = now_local().date()
    dbl_cal = calendar_map(db, first, last)   # дни двойной оплаты — маркер ×2 в шапке сетки
    # справочники и записи блоков — ОДНИМ запросом на всю сетку: без этого каждая
    # ячейка (N сотрудников × 31 день) делала три точечных запроса к БД
    catalog = ShiftCatalog.load(db)
    block_index = BlockIndex.from_assignments(blocks)
    rows = []
    for emp in employees:
        periods = per_emp_periods.get(emp.id) or []
        cells = {}
        planned_total = 0.0
        work_days = 0
        fact_total = 0.0
        for d in days:
            employed = employed_on(periods, d) if periods else True
            entry = emap.get((emp.id, d))
            shift = entry_shift(db, entry, catalog=catalog) if entry else None
            auto = False
            if shift is None:
                shift = base_shift(db, emp, d, base_cfg, employed=employed,
                                   index=block_index, catalog=catalog)
                auto = shift is not None
            planned = shift.planned_hours if (shift and employed) else 0.0
            planned_total += planned
            work_days += 1 if (shift and shift.kind == "work" and employed) else 0
            trow = fmap.get((emp.id, d))
            fact_hours_v = trow.fact_hours if trow else 0.0
            fact_total += fact_hours_v
            worked_off = bool(fact_hours_v) and employed and (shift is None or shift.kind != "work")
            fact = fact_map.get((emp.id, d.isoformat()))
            if fact is not None:
                fact = {k: v for k, v in fact.items() if k not in ("raw", "plan_segments")}
            cells[d.isoformat()] = {
                "shift": _shift_brief(shift),
                "auto": auto,
                "note": entry.note if entry else "",
                "planned_hours": planned,
                "fact_hours": fact_hours_v,
                "worked_off": worked_off,
                "employed": employed,
                "partial": _partial_brief(entry),
                "punch_in_override": entry.punch_in_override if entry else None,
                "punch_out_override": entry.punch_out_override if entry else None,
                "fact": fact,
                "is_today": d == today,
                "is_future": d > today,
            }
        emp_blocks = grouped.get(emp.id) or (
            [{"group": normalize_group(emp.schedule_group), "start": first.isoformat(), "end": None,
              "ranges": [{"start": first.isoformat(), "end": None}], "pattern_label": ""}]
            if emp.schedule_group else [])
        rows.append({
            "employee": {
                "id": emp.id, "full_name": emp.full_name, "short_name": emp.display_name,
                "full_name_genitive": emp.full_name_genitive or suggest_genitive(emp.full_name),
                "position": emp.position, "tab_number": emp.tab_number or "",
                "balance_hours": emp.balance_hours,
                "schedule_group": normalize_group(emp.schedule_group) or "",
                "group_color": emp.group_color or "#8a94a6",
                "schedule_pattern": emp.schedule_pattern or "",
                "active": emp.active,
                "hired_at": emp.hired_at.isoformat() if emp.hired_at else None,
                "dismissed_at": emp.dismissed_at.isoformat() if emp.dismissed_at else None,
            },
            "blocks": emp_blocks,
            "employed_ranges": ranges_from_periods(periods, first, last),
            "cells": cells,
            "totals": {"planned_hours": round(planned_total, 2), "work_days": work_days,
                       "fact_hours": round(fact_total, 2)},
        })

    payload = {
        "year": year, "month": month, "month_name": month_name(month),
        "days": [{"date": d.isoformat(), "day": d.day, "weekday": WD_SHORT[d.weekday()],
                  "is_weekend": d.weekday() >= 5, "is_today": d == today,
                  "double_scope": dbl_cal.get(d, ""),
                  "double_title": (SCOPE_TITLES.get(dbl_cal.get(d, ""), "")
                                   if dbl_cal.get(d) else "")} for d in days],
        "rows": rows,
        "today": today.isoformat(),
        "readonly": not principal.is_manager,
        "colors": {"out_of_block": OUT_OF_BLOCK_COLOR, "worked_off": WORKED_OFF_COLOR,
                   "inactive": INACTIVE_COLOR},
    }
    if not principal.is_manager:
        _strip_to_plan(payload)      # батлеры видят только план смен
    return payload



class CellIn(BaseModel):
    employee_id: int
    date: dt.date
    shift_type_id: Optional[int] = None
    note: str = ""
    # частичное отсутствие внутри рабочей смены («отпросился с 14:00 до 16:00»)
    partial_shift_id: Optional[int] = None
    from_time: str = ""
    until_time: str = ""
    # явный override «можно ли жать Пришёл/Ушёл» (None — как в словаре вида смены)
    punch_in_override: Optional[bool] = None
    punch_out_override: Optional[bool] = None


def _clean_times(from_time: str, until_time: str) -> tuple[str, str]:
    ft, ut = (from_time or "").strip(), (until_time or "").strip()
    if bool(ft) != bool(ut):
        raise HTTPException(status_code=422,
                            detail="Укажите и время начала, и время конца отсутствия (или очистите оба поля)")
    if ft and not _HHMM.match(ft):
        raise HTTPException(status_code=422, detail="Время начала должно быть в формате ЧЧ:ММ")
    if ut and not _HHMM.match(ut):
        raise HTTPException(status_code=422, detail="Время конца должно быть в формате ЧЧ:ММ")
    if ft and ut and ft == ut:
        raise HTTPException(status_code=422, detail="Начало и конец отсутствия совпадают")
    return ft, ut


def _assert_day_active(db: Session, emp: Employee, date: dt.date) -> None:
    """День должен попадать в период работы сотрудника и в его активный блок графика."""
    periods = periods_of(db, emp.id)
    if not periods:
        periods = ensure_periods(db, emp)
    if not employed_on(periods, date):
        raise HTTPException(status_code=409,
                            detail="День неактивен: сотрудник не работал в эту дату "
                                   "(до приёма, после увольнения или между периодами работы)")
    if not _block_active(db, emp.id, date):
        raise HTTPException(status_code=409,
                            detail="День неактивен: сотрудник относится к другому блоку графика в эту дату")


def _apply_cell(db: Session, principal: Principal, payload: CellIn) -> Optional[ScheduleEntry]:
    emp = db.get(Employee, payload.employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    _assert_day_active(db, emp, payload.date)
    shift = db.get(ShiftType, payload.shift_type_id) if payload.shift_type_id else None
    if payload.shift_type_id and not shift:
        raise HTTPException(status_code=404, detail="Тип смены не найден")

    ft, ut = _clean_times(payload.from_time, payload.until_time)
    partial_shift = None
    if ft and ut:
        # частичное отсутствие возможно только внутри РАБОЧЕЙ смены:
        # если ячейка пустая — берём смену, которую считает базовый цикл/шаблон блока
        if shift is None:
            virtual = base_shift(db, emp, payload.date)
            if virtual is not None and virtual.kind == "work":
                shift = db.get(ShiftType, virtual.id)
        if shift is None or shift.kind != "work":
            raise HTTPException(status_code=422,
                                detail="«Отпросился» можно поставить только на рабочую смену")
        if payload.partial_shift_id:
            partial_shift = db.get(ShiftType, payload.partial_shift_id)
            if partial_shift is None:
                raise HTTPException(status_code=404, detail="Причина отсутствия не найдена")
            if partial_shift.kind != "absence":
                raise HTTPException(status_code=422,
                                    detail="Причиной частичного отсутствия может быть только вид отсутствия")

    entry = db.scalar(select(ScheduleEntry).where(
        ScheduleEntry.employee_id == payload.employee_id, ScheduleEntry.date == payload.date))

    if shift is None and not payload.note and not ft:
        if entry:
            db.delete(entry)
            audit(db, principal, "schedule_clear", f"employee:{emp.id}:{payload.date}")
            db.flush()
            recalc_day(db, emp, payload.date, commit=False)
        return None

    if entry is None:
        entry = ScheduleEntry(employee_id=emp.id, date=payload.date, shift_type=shift,
                              note=payload.note, updated_by=principal.user.id, updated_at=utcnow(),
                              punch_in_override=payload.punch_in_override,
                              punch_out_override=payload.punch_out_override)
        db.add(entry)
    else:
        before = {"shift": entry.shift_type.code if entry.shift_type else None, "note": entry.note}
        if shift is not None:
            entry.shift_type = shift
        if shift is not None and shift.kind != "work":
            ft = ut = ""                      # у отсутствия не бывает «окна отпросился»
            partial_shift = None
            entry.partial_shift_id = None
        entry.note = payload.note
        entry.punch_in_override = payload.punch_in_override
        entry.punch_out_override = payload.punch_out_override
        entry.updated_by = principal.user.id
        entry.updated_at = utcnow()
        audit(db, principal, "schedule_update", f"employee:{emp.id}:{payload.date}",
              {"before": before, "after": {"shift": shift.code if shift else None, "note": entry.note}})
    entry.from_time = ft
    entry.until_time = ut
    entry.partial_shift_id = partial_shift.id if partial_shift else (
        entry.partial_shift_id if (ft and entry.partial_shift_id) else None)
    if ft:
        audit(db, principal, "schedule_partial", f"employee:{emp.id}:{payload.date}",
              {"window": f"{ft}-{ut}", "reason": partial_shift.code if partial_shift else "",
               "hours": gap_hours(entry, payload.date)})
    db.flush()
    recalc_day(db, emp, payload.date, commit=False)
    return entry


def _cell_response(db: Session, emp_id: int, date: dt.date,
                   entry: Optional[ScheduleEntry]) -> dict:
    shift = entry_shift(db, entry) if entry else None
    rules = load_rules(db)
    p_start, p_end = shift_window(shift, date, rules) if shift else (None, None)
    return {
        "employee_id": emp_id,
        "date": date.isoformat(),
        "shift": _shift_brief(shift) if entry else None,
        "note": entry.note if entry else "",
        "partial": _partial_brief(entry),
        "punch_in_override": entry.punch_in_override if entry else None,
        "punch_out_override": entry.punch_out_override if entry else None,
        "planned_hours": (shift.planned_hours if (shift and entry) else 0.0),
        "planned_start": p_start.isoformat(timespec="minutes") if (p_start and entry) else None,
        "planned_end": p_end.isoformat(timespec="minutes") if (p_end and entry) else None,
    }


@router.put("/cell")
def set_cell(payload: CellIn, principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    entry = _apply_cell(db, principal, payload)
    db.commit()
    return {"ok": True, "cell": _cell_response(db, payload.employee_id, payload.date, entry)}


class BulkCellIn(BaseModel):
    employee_id: int
    date: dt.date
    shift_type_id: Optional[int] = None
    note: str = ""
    partial_shift_id: Optional[int] = None
    from_time: str = ""
    until_time: str = ""


@router.post("/bulk")
def set_bulk(payload: list[BulkCellIn], principal: Principal = Depends(require_manager),
             db: Session = Depends(get_db)):
    for item in payload:
        _apply_cell(db, principal, CellIn(**item.model_dump()))
    audit(db, principal, "schedule_bulk", f"cells:{len(payload)}")
    db.commit()
    return {"ok": True, "updated": len(payload)}


# ─────────────────── отсутствие на период любой длины (баг №1) ───────────────────
class RangeAbsenceIn(BaseModel):
    employee_ids: list[int]
    start: dt.date
    end: dt.date
    shift_type_id: int
    note: str = ""
    only_work_days: bool = False     # только на рабочие по графику дни (отгулы, отпуск за свой счёт)
    # явный override «можно ли жать Пришёл/Ушёл» на весь период (None — как в словаре)
    punch_in_override: Optional[bool] = None
    punch_out_override: Optional[bool] = None


@router.post("/range-absence")
def range_absence(payload: RangeAbsenceIn, principal: Principal = Depends(require_manager),
                  db: Session = Depends(get_db)):
    """Назначить отсутствие сразу на период — в т.ч. через границы месяцев.

    Дни вне периодов работы (уволен/не принят) и дни чужого блока пропускаются.
    `only_work_days` — ставить только туда, где по графику рабочая смена
    («выходной за часы», отпуск за свой счёт на рабочие дни)."""
    if payload.end < payload.start:
        raise HTTPException(status_code=422, detail="Дата окончания раньше даты начала")
    if (payload.end - payload.start).days > 366:
        raise HTTPException(status_code=422, detail="Период длиннее года — назначьте его частями")
    shift = db.get(ShiftType, payload.shift_type_id)
    if not shift:
        raise HTTPException(status_code=404, detail="Вид отсутствия не найден")
    if not payload.employee_ids:
        raise HTTPException(status_code=422, detail="Не выбран ни один сотрудник")

    emps = {e.id: e for e in db.scalars(select(Employee).where(
        Employee.id.in_(payload.employee_ids)))}
    updated = skipped_inactive = skipped_off = 0
    day = payload.start
    while day <= payload.end:
        for emp_id, emp in emps.items():
            periods = periods_of(db, emp_id) or ensure_periods(db, emp)
            if not employed_on(periods, day) or not _block_active(db, emp_id, day):
                skipped_inactive += 1
                continue
            if payload.only_work_days:
                entry0 = db.scalar(select(ScheduleEntry).where(
                    ScheduleEntry.employee_id == emp_id, ScheduleEntry.date == day))
                planned = entry_shift(db, entry0) if entry0 else base_shift(db, emp, day)
                if not (planned and planned.kind == "work"):
                    skipped_off += 1
                    continue
            entry = db.scalar(select(ScheduleEntry).where(
                ScheduleEntry.employee_id == emp_id, ScheduleEntry.date == day))
            if entry is None:
                entry = ScheduleEntry(employee_id=emp_id, date=day, updated_by=principal.user.id)
                db.add(entry)
            entry.shift_type_id = shift.id
            entry.note = payload.note
            entry.partial_shift_id = None
            entry.from_time = ""
            entry.until_time = ""
            entry.punch_in_override = payload.punch_in_override
            entry.punch_out_override = payload.punch_out_override
            entry.updated_by = principal.user.id
            entry.updated_at = utcnow()
            updated += 1
        day += dt.timedelta(days=1)

    months = sorted({(payload.start + dt.timedelta(days=i)).strftime("%Y-%m")
                     for i in range((payload.end - payload.start).days + 1)})
    audit(db, principal, "schedule_range_absence",
          f"{shift.code}:{payload.start}..{payload.end}",
          {"employees": payload.employee_ids, "updated": updated,
           "only_work_days": payload.only_work_days, "months": months})
    db.flush()
    recalc_range(db, payload.start, payload.end, employee_ids=payload.employee_ids, commit=False)
    db.commit()
    return {"ok": True, "updated": updated,
            "skipped_inactive": skipped_inactive, "skipped_off": skipped_off,
            "months": months}


@router.get("/absence-period")
def absence_period(employee_id: int, date: dt.date,
                   principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Непрерывный период одного отсутствия вокруг даты — для печати заявления.

    В отличие от поиска «в пределах открытого месяца» период находится целиком,
    даже если отпуск начинается в одном месяце, а заканчивается в следующем (баг №1)."""
    entries = db.scalars(select(ScheduleEntry).where(
        ScheduleEntry.employee_id == employee_id).order_by(ScheduleEntry.date)).all()
    by_date = {e.date: e for e in entries}
    anchor = by_date.get(date)
    if anchor is None:
        raise HTTPException(status_code=404, detail="В эту дату нет назначенного отсутствия")

    start = end = date
    d = date - dt.timedelta(days=1)
    while d in by_date and by_date[d].shift_type_id == anchor.shift_type_id:
        start = d
        d -= dt.timedelta(days=1)
    d = date + dt.timedelta(days=1)
    while d in by_date and by_date[d].shift_type_id == anchor.shift_type_id:
        end = d
        d += dt.timedelta(days=1)

    shift = entry_shift(db, anchor)
    emp = db.get(Employee, employee_id)
    return {
        "employee": None if not emp else {
            "id": emp.id, "full_name": emp.full_name, "short_name": emp.display_name,
            "full_name_genitive": emp.full_name_genitive or suggest_genitive(emp.full_name),
            "position": emp.position, "tab_number": emp.tab_number or "",
            "nationality": emp.nationality or "", "subdivision": emp.subdivision or "",
            "department": emp.department.name if emp.department else "",
        },
        "start": start.isoformat(), "end": end.isoformat(),
        "days": (end - start).days + 1,
        "shift": _shift_brief(shift),
        "note": anchor.note or "",
        "partial": _partial_brief(anchor),
        "notes": sorted({e.note for e in entries if start <= e.date <= end and e.note}),
    }


class PatternIn(BaseModel):
    employee_ids: list[int]
    start_date: dt.date
    end_date: dt.date
    work_shift_id: int
    off_shift_id: Optional[int] = None
    pattern: str = "2/2"
    cycle: str = ""
    off_weekdays: list[int] = [5, 6]
    offset: int = 0
    only_empty: bool = False
    sync_blocks: bool = True     # для Смены 1/Смены 2: инверсия фазы, пересечений нет


@router.post("/fill-pattern")
def fill_pattern(payload: PatternIn, principal: Principal = Depends(require_manager),
                 db: Session = Depends(get_db)):
    """Заполнить период циклом (2/2, 4/3, 5/2 с выбором выходных, произвольная строка).
    Для блоков «Смена 1»/«Смена 2» включена инверсия фазы: пересечений не будет.
    Дни, когда сотрудник не работал в компании, пропускаются."""
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail="Дата окончания раньше даты начала")
    work_shift = db.get(ShiftType, payload.work_shift_id)
    if not work_shift:
        raise HTTPException(status_code=404, detail="Рабочая смена не найдена")
    off_shift = db.get(ShiftType, payload.off_shift_id) if payload.off_shift_id else None
    ndays = (payload.end_date - payload.start_date).days + 1
    try:
        flags = pattern_days(payload.pattern, payload.start_date, ndays, payload.offset,
                             off_weekdays=payload.off_weekdays, cycle=payload.cycle)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    emps = {e.id: e for e in db.scalars(select(Employee).where(Employee.id.in_(payload.employee_ids)))}

    # инверсия фазы между Сменой 1 и Сменой 2: день, когда работает другая смена, — выходной
    if payload.sync_blocks:
        group_of = {eid: normalize_group(emps[eid].schedule_group) if eid in emps else ""
                    for eid in payload.employee_ids}
        involved = {g for g in group_of.values() if g in ("Смена 1", "Смена 2")}
        if involved:
            other_groups = {"Смена 1", "Смена 2"} - involved or {"Смена 1", "Смена 2"}
            other_ids = [e.id for e in db.scalars(select(Employee).where(
                Employee.schedule_group.in_(list(other_groups)), Employee.deleted_at.is_(None)))]
            if other_ids:
                other_entries = db.scalars(select(ScheduleEntry).where(
                    ScheduleEntry.employee_id.in_(other_ids),
                    ScheduleEntry.date >= payload.start_date,
                    ScheduleEntry.date <= payload.end_date)).all()
                other_work_days = {e.date for e in other_entries
                                   if e.shift_type and e.shift_type.kind == "work"}
                other_off_days = {e.date for e in other_entries}
                for i in range(ndays):
                    d = payload.start_date + dt.timedelta(days=i)
                    if d in other_work_days:
                        flags[i] = False
                    elif d in other_off_days:
                        flags[i] = True

    existing = {(e.employee_id, e.date): e for e in db.scalars(select(ScheduleEntry).where(
        ScheduleEntry.date >= payload.start_date, ScheduleEntry.date <= payload.end_date,
        ScheduleEntry.employee_id.in_(payload.employee_ids)))}

    changed = 0
    for emp_id in payload.employee_ids:
        emp = emps.get(emp_id)
        if not emp:
            continue
        periods = periods_of(db, emp_id) or ensure_periods(db, emp)
        for i in range(ndays):
            date = payload.start_date + dt.timedelta(days=i)
            if not employed_on(periods, date):
                continue
            shift = work_shift if flags[i] else off_shift
            if shift is None:
                continue
            entry = existing.get((emp_id, date))
            if payload.only_empty and entry is not None:
                continue
            if entry is None:
                entry = ScheduleEntry(employee_id=emp_id, date=date, shift_type=shift,
                                      updated_by=principal.user.id, updated_at=utcnow())
                db.add(entry)
            else:
                if entry.shift_type_id == shift.id:
                    continue
                entry.shift_type = shift
                entry.updated_by = principal.user.id
                entry.updated_at = utcnow()
            changed += 1
        # запоминаем цикл сотрудника, чтобы продолжать его в следующие месяцы
        emp.schedule_pattern = f"custom:{payload.cycle}" if payload.pattern.lower() == "custom" else payload.pattern
        emp.schedule_anchor = payload.start_date
    audit(db, principal, "schedule_fill_pattern",
          f"{payload.pattern}:{payload.start_date}..{payload.end_date}",
          {"employees": payload.employee_ids, "changed": changed, "sync_blocks": payload.sync_blocks})
    db.flush()
    recalc_range(db, payload.start_date, payload.end_date, employee_ids=payload.employee_ids, commit=False)
    db.commit()
    return {"ok": True, "changed": changed}


class ContinueIn(BaseModel):
    year: int
    month: int
    employee_ids: Optional[list[int]] = None
    only_empty: bool = False


@router.post("/continue")
def continue_schedule(payload: ContinueIn, principal: Principal = Depends(require_manager),
                      db: Session = Depends(get_db)):
    """Продолжить график на месяц НЕ копированием, а продолжением цикла каждого сотрудника
    (2/2, 5/2, custom…) от его точки отсчёта — фазы смен 1/2 сохраняются."""
    first, last = _month_bounds(payload.year, payload.month)
    stmt = select(Employee).where(Employee.active.is_(True), Employee.deleted_at.is_(None),
                                  Employee.schedule_pattern != "")
    if payload.employee_ids:
        stmt = stmt.where(Employee.id.in_(payload.employee_ids))
    emps = db.scalars(stmt).all()
    if not emps:
        raise HTTPException(status_code=422,
                            detail="Ни у одного сотрудника не сохранён цикл: заполните месяц через «Заполнить графиком»")

    off_shift = db.scalar(select(ShiftType).where(ShiftType.is_default_off.is_(True)))
    changed = 0
    for emp in emps:
        pattern = emp.schedule_pattern
        cycle = ""
        if pattern.startswith("custom:"):
            pattern, cycle = "custom", pattern[7:]
        anchor = emp.schedule_anchor or first
        # обычная рабочая смена сотрудника: самая частая рабочая смена за прошлый месяц
        prev_first, prev_last = _month_bounds(payload.year - 1 if payload.month == 1 else payload.year,
                                              payload.month - 1 if payload.month > 1 else 12)
        counts: dict[int, int] = {}
        for e in db.scalars(select(ScheduleEntry).where(
                ScheduleEntry.employee_id == emp.id,
                ScheduleEntry.date >= prev_first, ScheduleEntry.date <= prev_last)):
            st = e.shift_type
            if st and st.kind == "work":
                counts[st.id] = counts.get(st.id, 0) + 1
        work_shift = db.get(ShiftType, max(counts, key=counts.get)) if counts else None
        if work_shift is None:
            work_shift = db.scalar(select(ShiftType).where(ShiftType.kind == "work")
                                   .order_by(ShiftType.sort_order))
        if work_shift is None or off_shift is None:
            continue

        total_days = (last - anchor).days + 1
        if total_days <= 0:
            continue
        try:
            flags = pattern_days(pattern, anchor, total_days, 0, cycle=cycle)
        except ValueError:
            continue
        month_flags = flags[(first - anchor).days:]
        for i, is_work in enumerate(month_flags):
            date = first + dt.timedelta(days=i)
            if date > last:
                break
            if not is_employed(db, emp, date):
                continue
            shift = work_shift if is_work else off_shift
            entry = db.scalar(select(ScheduleEntry).where(
                ScheduleEntry.employee_id == emp.id, ScheduleEntry.date == date))
            if payload.only_empty and entry is not None:
                continue
            if entry is None:
                db.add(ScheduleEntry(employee_id=emp.id, date=date, shift_type=shift,
                                     updated_by=principal.user.id, updated_at=utcnow()))
                changed += 1
            elif entry.shift_type_id != shift.id:
                entry.shift_type = shift
                entry.updated_by = principal.user.id
                entry.updated_at = utcnow()
                changed += 1
    audit(db, principal, "schedule_continue", f"{payload.year}-{payload.month:02d}", {"changed": changed})
    db.flush()
    recalc_range(db, first, last, commit=False)
    db.commit()
    return {"ok": True, "changed": changed}


class ClearMonthIn(BaseModel):
    year: int
    month: int


@router.post("/clear-month")
def clear_month(payload: ClearMonthIn, principal: Principal = Depends(require_manager),
                db: Session = Depends(get_db)):
    """Обнулить график на указанный месяц (ячейки удаляются, табель пересчитывается)."""
    first, last = _month_bounds(payload.year, payload.month)
    entries = db.scalars(select(ScheduleEntry).where(
        ScheduleEntry.date >= first, ScheduleEntry.date <= last)).all()
    n = len(entries)
    for e in entries:
        db.delete(e)
    audit(db, principal, "schedule_clear_month", f"{payload.year}-{payload.month:02d}", {"deleted": n})
    db.flush()
    recalc_range(db, first, last, commit=False)
    db.commit()
    return {"ok": True, "deleted": n}


class CopyIn(BaseModel):
    employee_ids: list[int]
    src_start: dt.date
    src_end: dt.date
    dst_start: dt.date
    only_empty: bool = False


@router.post("/copy")
def copy_period(payload: CopyIn, principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Прямое копирование периода (для особых случаев); основное средство — «Продолжить график»."""
    src_len = (payload.src_end - payload.src_start).days + 1
    if src_len <= 0:
        raise HTTPException(status_code=422, detail="Некорректный исходный период")
    src = {(e.employee_id, e.date): e for e in db.scalars(select(ScheduleEntry).where(
        ScheduleEntry.employee_id.in_(payload.employee_ids),
        ScheduleEntry.date >= payload.src_start, ScheduleEntry.date <= payload.src_end))}
    dst_existing = {(e.employee_id, e.date) for e in db.scalars(select(ScheduleEntry).where(
        ScheduleEntry.employee_id.in_(payload.employee_ids),
        ScheduleEntry.date >= payload.dst_start,
        ScheduleEntry.date <= payload.dst_start + dt.timedelta(days=src_len - 1)))}

    changed = 0
    for emp_id in payload.employee_ids:
        for i in range(src_len):
            s_entry = src.get((emp_id, payload.src_start + dt.timedelta(days=i)))
            if not s_entry:
                continue
            d_date = payload.dst_start + dt.timedelta(days=i)
            if payload.only_empty and (emp_id, d_date) in dst_existing:
                continue
            entry = db.scalar(select(ScheduleEntry).where(
                ScheduleEntry.employee_id == emp_id, ScheduleEntry.date == d_date))
            if entry is None:
                db.add(ScheduleEntry(employee_id=emp_id, date=d_date,
                                     shift_type_id=s_entry.shift_type_id, note=s_entry.note,
                                     partial_shift_id=s_entry.partial_shift_id,
                                     from_time=s_entry.from_time, until_time=s_entry.until_time,
                                     updated_by=principal.user.id, updated_at=utcnow()))
            else:
                entry.shift_type_id = s_entry.shift_type_id
                entry.note = s_entry.note
                entry.partial_shift_id = s_entry.partial_shift_id
                entry.from_time = s_entry.from_time
                entry.until_time = s_entry.until_time
                entry.updated_by = principal.user.id
                entry.updated_at = utcnow()
            changed += 1
    audit(db, principal, "schedule_copy",
          f"{payload.src_start}..{payload.src_end} → {payload.dst_start}", {"changed": changed})
    db.flush()
    recalc_range(db, payload.dst_start, payload.dst_start + dt.timedelta(days=src_len - 1),
                 employee_ids=payload.employee_ids, commit=False)
    db.commit()
    return {"ok": True, "changed": changed}


@router.get("/patterns")
def get_patterns(principal: Principal = Depends(require_manager)):
    return pattern_list()


@router.get("/today-board")
def today_board(principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    today = now_local().date()
    entries = db.scalars(select(ScheduleEntry).where(ScheduleEntry.date == today)).all()
    rules = load_rules(db)
    result = []
    for e in entries:
        s = entry_shift(db, e)          # смена такой, какой она была в эту дату (история словаря)
        if not s or s.kind != "work":
            continue
        p_start, p_end = shift_window(s, today, rules)
        result.append({
            "employee": {"id": e.employee.id, "short_name": e.employee.display_name,
                         "full_name": e.employee.full_name, "position": e.employee.position},
            "shift": _shift_brief(s),
            "planned_start": p_start.isoformat(timespec="minutes") if p_start else None,
            "planned_end": p_end.isoformat(timespec="minutes") if p_end else None,
            "note": e.note,
            "partial": _partial_brief(e),
        })
    result.sort(key=lambda x: x["planned_start"] or "")
    return {"date": today.isoformat(), "items": result}


# ─────────────────────────── экспорт сетки в Excel ───────────────────────────
@router.get("/xlsx")
def export_xlsx(year: int, month: int, principal: Principal = Depends(require_manager),
                db: Session = Depends(get_db)):
    """График на месяц в Excel: блоки смен, цветовая заливка ячеек, «чужие» дни при переходах."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(status_code=500, detail="Для выгрузки установите openpyxl: pip install openpyxl")

    data = get_grid(year, month, principal, db)
    first, last = _month_bounds(year, month)
    ndays = (last - first).days + 1

    wb = Workbook()
    ws = wb.active
    ws.title = f"График {data['month_name']} {year}"
    thin = Side(style="thin", color="D0D7E2")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor="E8EEF7")
    weekend_fill = PatternFill("solid", fgColor="F4F6FA")
    center = Alignment(horizontal="center", vertical="center")

    ws["A1"] = f"График сменности, {data['month_name']} {year} г."
    ws["A1"].font = Font(bold=True, size=13)
    hr = 3
    ws.cell(row=hr, column=1, value="Сотрудник").font = Font(bold=True, size=9)
    ws.cell(row=hr, column=1).fill = head_fill
    ws.cell(row=hr, column=1).border = border
    for i in range(ndays):
        d = first + dt.timedelta(days=i)
        c = ws.cell(row=hr, column=2 + i, value=f"{d.day:02d}\n{WD_SHORT[d.weekday()]}")
        c.font = Font(bold=True, size=8)
        c.fill = weekend_fill if d.weekday() >= 5 else head_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border
    c = ws.cell(row=hr, column=2 + ndays, value="Часов")
    c.font = Font(bold=True, size=9); c.fill = head_fill; c.alignment = center; c.border = border

    groups: dict[str, list[dict]] = {}
    for row in data["rows"]:
        for b in row["blocks"]:
            groups.setdefault(b["group"] or "Без группы", []).append(row)
    r_i = hr + 1
    for gname in sorted_groups(groups.keys()):
        gc = ws.cell(row=r_i, column=1, value=gname.upper())
        gc.font = Font(bold=True, size=10, color="44506B")
        for cc in range(1, 3 + ndays):
            ws.cell(row=r_i, column=cc).fill = PatternFill("solid", fgColor="EEF2F8")
        r_i += 1
        seen = set()
        for row in groups[gname]:
            if row["employee"]["id"] in seen and gname not in [b["group"] for b in row["blocks"]]:
                continue
            seen.add(row["employee"]["id"])
            block = next((b for b in row["blocks"] if b["group"] == gname), None)
            ranges = (block or {}).get("ranges") or []
            nc = ws.cell(row=r_i, column=1,
                         value=f"{row['employee']['full_name']}"
                               + (f" ({row['employee']['position']})" if row["employee"]["position"] else ""))
            nc.font = Font(size=10)
            nc.border = border
            for i in range(ndays):
                d = first + dt.timedelta(days=i)
                cell = row["cells"][d.isoformat()]
                iso = d.isoformat()
                out_of_block = bool(ranges) and not any(
                    rg["start"] <= iso and (not rg["end"] or iso <= rg["end"]) for rg in ranges)
                if not cell.get("employed", True):
                    fill, text = INACTIVE_COLOR, "—"
                elif out_of_block:
                    fill, text = OUT_OF_BLOCK_COLOR, "—"
                elif cell["worked_off"]:
                    fill, text = WORKED_OFF_COLOR, f"РАБ {cell['fact_hours']:g}"
                elif cell["shift"]:
                    fill = cell["shift"]["color"]
                    text = cell["shift"]["display_code"] or cell["shift"]["name"]
                    if cell.get("partial"):
                        text = f"{text}*"
                else:
                    fill, text = "FFFFFF", ""
                cc = ws.cell(row=r_i, column=2 + i, value=text)
                cc.alignment = center
                cc.border = border
                cc.font = Font(size=8, bold=True,
                               color="FFFFFF" if fill not in ("FFFFFF", OUT_OF_BLOCK_COLOR,
                                                              INACTIVE_COLOR, "#c3cdd9") else "44506B")
                if fill != "FFFFFF":
                    cc.fill = PatternFill("solid", fgColor=fill.replace("#", ""))
            tc = ws.cell(row=r_i, column=2 + ndays, value=row["totals"]["planned_hours"])
            tc.border = border; tc.alignment = center; tc.font = Font(size=9, bold=True)
            r_i += 1

    ws.column_dimensions["A"].width = 34
    for i in range(ndays):
        ws.column_dimensions[get_column_letter(2 + i)].width = 5.2
    ws.column_dimensions[get_column_letter(2 + ndays)].width = 7
    ws.freeze_panes = "B4"

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="grafik_{year}-{month:02d}.xlsx"'})


@router.get("/pdf")
def export_pdf(year: int, month: int, principal: Principal = Depends(current_principal),
               db: Session = Depends(get_db)):
    """График на месяц в PDF: та же таблица, что в «Печать»/Excel (блоки смен,
    цветные ячейки, коды смен, ×2 в шапке). Собирается через DOCX → PDF
    (LibreOffice или встроенный движок reportlab); без движка — 501 с подсказкой.
    Батлерам достаётся PDF ровно того плана, который они видят на экране
    (get_grid для них уже очищен от факта и начислений)."""
    from ..grid_docx import pdf_unavailable_detail, schedule_docx
    from ..pdf_render import docx_to_pdf

    data = get_grid(year, month, principal, db)
    pdf, how = docx_to_pdf(schedule_docx(data), f"grafik_{year}-{month:02d}.pdf")
    if pdf is None:
        raise HTTPException(status_code=501, detail=pdf_unavailable_detail(how))
    audit(db, principal, "schedule_pdf", f"{year}-{month:02d}", {"rows": len(data["rows"])})
    db.commit()
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="grafik_{year}-{month:02d}.pdf"'})
