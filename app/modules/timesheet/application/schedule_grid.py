"""Вкладка «График» (16.3): сетка месяца и её выгрузки.

График — производный документ: генерируется из Табеля по окнам CFG-WINDOWS
(source="generated"), ручные смены (source="manual") заменяют генерацию дня целиком;
день редактируем ⇔ accepts_ut(дня-якоря) = Да. «Разрез» смены — логический (v7/R17):
согласованное отсутствие — отдельная запись (UTC-интервал, может пересекать полночь),
хранимая смена физически не делится. Правки Графика — в ``schedule_edit.py``."""
from __future__ import annotations

import calendar
import datetime as dt
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transactional
from app.core.errors import NotSupported
from app.core.permissions import principal_permissions
from app.core.time import TZ, local_date, local_iso, month_name, to_local
from app.modules.exchange.application.documents import docx_to_pdf, pdf_unavailable_detail, write_docx
from app.modules.exchange.application.tables import write_xlsx
from app.modules.people.application import (
    Employee,
    EmploymentPeriod,
    employed_on,
    group_index,
    normalize_group,
    ranges_from_periods,
    suggest_genitive,
)

from ..adapters.orm import BlockAssignment, ScheduleAbsence, ScheduleShift, ShiftType, TabelDay
from ..adapters.sql_settings import SqlSettingsAdapter
from ..domain.settings.types import Settings
from ..domain.types.entities import Period
from . import exports
from .doublepay import SCOPE_TITLES, calendar_map
from .engine_common import color_lookups, covers_window
from .months import month_period
from .period_params import ensure_period
from .texts import fmt_hours_strict

OUT_OF_BLOCK_COLOR = "#efe6d7"
WORKED_OFF_COLOR = "#e7f0e2"
INACTIVE_COLOR = "#f1f1f1"


def month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    last = calendar.monthrange(year, month)[1]
    return dt.date(year, month, 1), dt.date(year, month, last)


def month_bounds_utc(first: dt.date, last: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """Границы месяца как моменты: местная полночь первого дня и полночь после последнего."""
    return (dt.datetime.combine(first, dt.time(0), TZ).astimezone(dt.UTC),
            dt.datetime.combine(last + dt.timedelta(days=1), dt.time(0), TZ).astimezone(dt.UTC))


def period_settings(db: Session, period: Period) -> Settings:
    """Настройки расчёта периода; повреждённые настройки — ConfigError (ответ 409)."""
    return SqlSettingsAdapter(db).load(period)


def _shift_brief(row: ScheduleShift) -> dict:
    start, end = to_local(row.start_utc), to_local(row.end_utc)
    return {"source": row.source, "anchor": row.date.isoformat(),
            "start": local_iso(start, "auto"), "end": local_iso(end, "auto"),
            "start_hm": start.strftime("%H:%M"), "end_hm": end.strftime("%H:%M"),
            "note": row.note or "", "id": row.id}


def _absence_brief(row: ScheduleAbsence, kind: Optional[ShiftType],
                   whole_shift: bool = False) -> dict:
    start, end = to_local(row.start_utc), to_local(row.end_utc)
    return {"id": row.id, "start": local_iso(start, "auto"), "end": local_iso(end, "auto"),
            "start_hm": start.strftime("%H:%M"), "end_hm": end.strftime("%H:%M"),
            "note": row.note or "",
            # покрывает всё рабочее окно дня — «выходной за часы» (EX-29): сетка
            # рисует плашку на весь день вместо разрезанных отрезков смены
            "whole_shift": whole_shift,
            "kind": None if kind is None else
            {"id": kind.id, "code": kind.code, "name": kind.name, "color": kind.color,
             "doc_type": kind.doc_type or ""}}


def _cell_color(shifts: list, absences: list, trow: Optional[TabelDay], work_types: dict,
                code_colors: dict) -> Optional[str]:
    """Цвет ячейки Графика.

    Разрешается СЕРВЕРОМ, чтобы экран, браузерная печать, PDF и Excel красили
    одинаково: плашка «выходной за часы» — цвет вида отсутствия из словаря
    «Смены и отсутствия»; смена — цвет словарной смены с тем же окном (первая
    по id); день без смены (отсутствие кодом Табеля, выходной) — цвет кода
    Табеля из presentation настроек."""
    off = next((a for a in absences if a.get("whole_shift")), None)
    if off is not None:
        return (off.get("kind") or {}).get("color") or "#0e9aa7"
    if shifts:
        wt = work_types.get((shifts[0]["start_hm"], shifts[0]["end_hm"]))
        if wt is not None and (wt.color or "").strip():
            return wt.color
    if trow is not None:
        return code_colors.get(trow.code)
    return None


def _visible_segments(shift_rows: list, absence_rows: list) -> list[list[str]]:
    """Видимые части смен дня: смена МИНУС интервалы согласованных отсутствий.

    Разрез логический (v7/R17): записи смен не меняются, сетка показывает остаток —
    каждый отрезок с новой строки («08:00–12:00», «14:00–16:00», «17:00–20:00»).
    Моменты — реальные UTC-датавремя, поэтому отрезки через полночь режутся без
    особых случаев. Без отсутствий результат равен интервалам самих смен."""
    out: list[list[str]] = []
    for sh in shift_rows:
        segs = [(sh.start_utc, sh.end_utc)]
        for a in sorted(absence_rows, key=lambda r: r.start_utc):
            nxt = []
            for ss, se in segs:
                if a.end_utc <= ss or a.start_utc >= se:
                    nxt.append((ss, se))
                    continue
                if a.start_utc > ss:
                    nxt.append((ss, a.start_utc))
                if a.end_utc < se:
                    nxt.append((a.end_utc, se))
            segs = nxt
        hm = lambda v: to_local(v).strftime("%H:%M")  # noqa: E731
        out.extend([[hm(ss), hm(se)] for ss, se in segs])
    return out


def _position_rank(position: Optional[str]) -> int:
    """Порядок внутри блока: старшие («Старший
    батлер» и т.п.) впереди остальных, дальше — алфавит. Работает на всех стоках
    сетки разом (экран, печать, PDF, Excel), потому что порядок задаётся здесь."""
    return 0 if position and "старш" in position.lower() else 1


def visible_employees(db: Session, first: dt.date,
                       last: dt.date) -> tuple[list[Employee], dict[int, list]]:
    """Сотрудники месяца + их периоды работы (батч, без N+1)."""
    candidates = db.scalars(select(Employee).where(Employee.deleted_at.is_(None))).all()
    all_periods = db.scalars(select(EmploymentPeriod).where(
        EmploymentPeriod.employee_id.in_([e.id for e in candidates]))).all() if candidates else []
    per_emp: dict[int, list] = {}
    for p in all_periods:
        per_emp.setdefault(p.employee_id, []).append(p)

    def visible(emp: Employee) -> bool:
        recs = per_emp.get(emp.id)
        if not recs:
            return bool(emp.active)
        return any(p.start_date <= last and (p.end_date is None or p.end_date >= first)
                   for p in recs)

    out = [e for e in candidates if visible(e)]
    out.sort(key=lambda e: (group_index(normalize_group(e.schedule_group)),
                            _position_rank(e.position), e.full_name))
    return out, per_emp


_ABSENCE_PLAN_KEYS = ("start_hm", "end_hm", "whole_shift")


def _strip_to_plan(payload: dict) -> dict:
    """Батлеры видят только план: заметки, номера записей и служебные поля пусты (``None``)."""
    for row in payload["rows"]:
        for cell in row["cells"].values():
            cell["absences"] = [{k: (a[k] if k in _ABSENCE_PLAN_KEYS else None) for k in a}
                                for a in cell["absences"]]
            if cell.get("tabel"):
                cell["tabel"]["note"] = None
            for sh in cell["shifts"]:
                sh["note"] = None
                sh["id"] = None
    return payload


def grid(db: Session, principal: Principal, year: int, month: int) -> dict:
    """Сетка Графика: ФИО × дни месяца; ячейка — Табель-код, отрезки смен (generated/
    manual) и согласованные отсутствия (логический разрез).

    Без права «полные данные сетки» ячейки отдают только план: заметки и номера записей
    пусты."""
    ensure_period(year, month)
    first, last = month_bounds(year, month)
    period = month_period(year, month)
    days = [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]
    st = period_settings(db, period)

    employees, per_emp_periods = visible_employees(db, first, last)
    emp_ids = [e.id for e in employees]
    lo_utc, hi_utc = month_bounds_utc(first, last)

    shift_rows = db.scalars(select(ScheduleShift).where(
        ScheduleShift.employee_id.in_(emp_ids), ScheduleShift.start_utc < hi_utc,
        ScheduleShift.end_utc > lo_utc).order_by(ScheduleShift.start_utc)).all() if emp_ids else []
    absence_rows = db.scalars(select(ScheduleAbsence).where(
        ScheduleAbsence.employee_id.in_(emp_ids), ScheduleAbsence.start_utc < hi_utc,
        ScheduleAbsence.end_utc > lo_utc).order_by(ScheduleAbsence.start_utc)).all() \
        if emp_ids else []
    tabel_rows = {(r.employee_id, r.date): r for r in db.scalars(select(TabelDay).where(
        TabelDay.employee_id.in_(emp_ids), TabelDay.date >= first,
        TabelDay.date <= last))} if emp_ids else {}
    block_rows = db.scalars(select(BlockAssignment).where(
        BlockAssignment.employee_id.in_(emp_ids),
        BlockAssignment.start_date <= last)).all() if emp_ids else []
    blocks_by_emp: dict[int, list] = {}
    for b in block_rows:
        blocks_by_emp.setdefault(b.employee_id, []).append(b)
    kinds = {k.id: k for k in db.scalars(select(ShiftType).where(
        ShiftType.id.in_({a.kind_id for a in absence_rows if a.kind_id})))} \
        if absence_rows else {}
    # цвета ячеек — из словаря «Смены и отсутствия» (общий сервис: те же цвета
    # у Графика, Факта-Ганта и печатных форм)
    work_types, code_colors = color_lookups(db)
    shifts_by_emp_day: dict[tuple[int, str], list] = {}
    for row in shift_rows:
        start_local = row.start_utc.astimezone(TZ)
        end_local = row.end_utc.astimezone(TZ)
        day = start_local.date()
        while day <= min(end_local.date(), last):
            if first <= day <= last:
                shifts_by_emp_day.setdefault((row.employee_id, day.isoformat()), []).append(row)
            day += dt.timedelta(days=1)
    absences_by_emp_day: dict[tuple[int, str], list] = {}
    for row in absence_rows:
        start_local = row.start_utc.astimezone(TZ)
        end_local = row.end_utc.astimezone(TZ)
        day = start_local.date()
        while day <= min(end_local.date(), last):
            if first <= day <= last:
                absences_by_emp_day.setdefault((row.employee_id, day.isoformat()), []).append(row)
            day += dt.timedelta(days=1)

    today = local_date()
    dbl_cal = calendar_map(db, first, last)
    perms = principal_permissions(db, principal)
    rows = []
    for emp in employees:
        periods = per_emp_periods.get(emp.id) or []
        cells = {}
        planned_total = 0.0
        work_days = 0
        for d in days:
            employed = employed_on(periods, d) if periods else True
            trow = tabel_rows.get((emp.id, d))
            sh_rows = shifts_by_emp_day.get((emp.id, d.isoformat()), [])
            ab_rows = absences_by_emp_day.get((emp.id, d.isoformat()), [])
            policy = st.day_code_policy.get(trow.code) if trow else None
            value = None
            if trow:
                value = (f"{trow.code} {fmt_hours_strict(trow.plan_minutes, emp.id, d)}"
                         if policy and policy.carries_hours else trow.code)
            planned = (trow.plan_minutes / 60) if trow else 0.0
            planned_total += planned
            work_days += 1 if (policy and policy.carries_hours) else 0
            shifts_brief = [_shift_brief(r) for r in sh_rows]
            absences_brief = [_absence_brief(r, kinds.get(r.kind_id),
                                             absence_covers_day(st, tabel_rows, emp.id, r))
                              for r in ab_rows]
            cells[d.isoformat()] = {
                "tabel": None if trow is None else
                {"code": trow.code, "value": value, "hours": trow.plan_minutes / 60,
                 "source": trow.source, "note": trow.note or ""},
                "shifts": shifts_brief,
                # видимые отрезки смены (минус отсутствия) — по строке на отрезок
                "segments": _visible_segments(sh_rows, ab_rows),
                "absences": absences_brief,
                "color": _cell_color(shifts_brief, absences_brief, trow,
                                     work_types, code_colors),
                "planned_hours": planned,
                "employed": employed,
                # день редактируем (ручная смена) ⇔ accepts_ut кода Табеля (16.3)
                "editable": bool(policy and policy.accepts_ut),
                "is_today": d == today,
                "is_future": d > today,
            }
        emp_blocks = _block_ranges(blocks_by_emp.get(emp.id, []), emp, first, last)
        rows.append({
            "employee": {
                "id": emp.id, "full_name": emp.full_name, "short_name": emp.display_name,
                "full_name_genitive": emp.full_name_genitive or suggest_genitive(emp.full_name),
                "position": emp.position, "tab_number": emp.tab_number or "",
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
            "totals": {"planned_hours": round(planned_total, 2), "work_days": work_days},
        })

    payload = {
        "year": year, "month": month, "month_name": month_name(month),
        "days": [{"date": d.isoformat(), "day": d.day,
                  "weekday": ["пн", "вт", "ср", "чт", "пт", "сб", "вс"][d.weekday()],
                  "is_weekend": d.weekday() >= 5, "is_today": d == today,
                  "double_scope": dbl_cal.get(d, ""),
                  "double_title": SCOPE_TITLES.get(dbl_cal.get(d, ""), "") if dbl_cal.get(d) else ""}
                 for d in days],
        "rows": rows,
        "today": today.isoformat(),
        "readonly": "schedule.edit" not in perms,
        "colors": {"out_of_block": OUT_OF_BLOCK_COLOR, "worked_off": WORKED_OFF_COLOR,
                   "inactive": INACTIVE_COLOR},
    }
    if "schedule.view_all" not in perms:
        # скоуп сетки — по ключу schedule.view_all (бывш. is_manager, §5.2)
        _strip_to_plan(payload)
    return payload


def _block_ranges(blocks, emp: Employee, first: dt.date, last: dt.date) -> list[dict]:
    per_group: dict[str, list[dict]] = {}
    labels: dict[str, str] = {}
    for b in blocks:
        if b.end_date and b.end_date < first:
            continue
        g = normalize_group(b.group)
        per_group.setdefault(g, []).append(
            {"start": b.start_date.isoformat(),
             "end": b.end_date.isoformat() if b.end_date else None})
        lbl = b.pattern.get("label") or ""
        if lbl:
            labels[g] = lbl
    return [{"group": g, "ranges": rs, "pattern_label": labels.get(g, "")}
            for g, rs in per_group.items()] or \
        [{"group": normalize_group(emp.schedule_group), "ranges": [], "pattern_label": ""}]


def absence_covers_day(st, tabel_rows: dict, employee_id: int,
                        row: ScheduleAbsence) -> bool:
    """whole_shift для строки сетки: окно берём у дня-якоря отсутствия (у смены
    через полночь якорь — день начала)."""
    start_local = row.start_utc.astimezone(TZ)
    end_local = row.end_utc.astimezone(TZ)
    day = start_local.date()
    return covers_window(st, tabel_rows.get((employee_id, day)), day, start_local, end_local)


def export_xlsx(db: Session, principal: Principal, year: int, month: int) -> tuple[bytes, str]:
    """График в Excel — форма ``exports.schedule_sheet``. Возвращает (файл, имя файла)."""
    data = grid(db, principal, year, month)
    return write_xlsx([exports.schedule_sheet(data, year, month)]), f"schedule_{year}_{month:02d}.xlsx"


@transactional
def export_pdf(db: Session, principal: Principal, year: int, month: int) -> tuple[bytes, str]:
    """График на месяц в PDF: та же таблица, что в «Печать» и Excel. Собирается через
    DOCX → PDF; если собрать не удалось — отказ 501 с подсказкой. Возвращает (файл, имя файла)."""
    data = grid(db, principal, year, month)
    filename = f"grafik_{year}-{month:02d}.pdf"
    pdf, how = docx_to_pdf(write_docx(exports.schedule_document(data)), filename)
    if pdf is None:
        raise NotSupported(pdf_unavailable_detail(how))
    audit(db, principal, "schedule_pdf", f"{year}-{month:02d}", {"rows": len(data["rows"])})
    return pdf, filename
