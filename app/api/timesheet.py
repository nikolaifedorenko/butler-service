"""Табель: итоги за месяц, детализация по дням, пересчёт, выгрузки CSV и XLSX (сетка «ДЯ/ДН»)."""
from __future__ import annotations

import datetime as dt
import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import Principal, audit, require_manager
from ..db import get_db
from ..deps import WD_SHORT, month_name, now_local
from ..doublepay import double_map_for
from ..models import Employee, TimesheetRow
from ..timesheet import bank_as_of, month_bounds, recalc_range, settle_overtime

router = APIRouter(prefix="/api/timesheet", tags=["timesheet"])

STATUS_TITLES = {
    "ok": "Без отклонений",
    "late": "Опоздание",
    "early": "Ранний уход",
    "late_early": "Опоздание и ранний уход",
    "no_punch": "Нет отметок (неявка?)",
    "unclosed": "Смена не закрыта",
    "off": "Выходной",
    "absence": "Отсутствие",
    "work_no_plan": "Работа вне графика",
    "work_off": "Работа в выходной",
    "planned": "Смена впереди (план)",
    "": "—",
}


class RecalcIn(BaseModel):
    year: int
    month: int
    employee_ids: Optional[list[int]] = None


def _totals_from_rows(rows: list[dict], opening_balance: float) -> dict:
    t = {"planned": 0.0, "fact": 0.0, "night": 0.0, "day": 0.0, "ot": 0.0,
         "deficit": 0.0, "timeoff": 0.0, "work_days": 0, "absence_days": 0, "issues": 0}
    for r in rows:
        t["planned"] += r["planned_hours"]
        t["fact"] += r["fact_hours"]
        t["night"] += r["night_hours"]
        t["day"] += r["day_hours"]
        t["ot"] += r["ot_hours"]
        t["deficit"] += r["deficit_hours"]
        t["timeoff"] += r["timeoff_hours"]
        if r["planned_hours"] > 0:
            t["work_days"] += 1
        if r["status"] == "absence":
            t["absence_days"] += 1
        if r["status"] in ("late", "early", "late_early", "no_punch", "unclosed", "work_no_plan"):
            t["issues"] += 1
    for k in list(t):
        if isinstance(t[k], float):
            t[k] = round(t[k], 2)
    t["balance"] = round(opening_balance + t["ot"] - t["timeoff"] - t["deficit"], 2)
    return t


def _build(db: Session, year: int, month: int, employee_ids: Optional[list[int]] = None) -> dict:
    first, last = month_bounds(year, month)
    employees = db.scalars(select(Employee).where(Employee.active.is_(True))
                           .order_by(Employee.schedule_group, Employee.full_name)).all()
    if employee_ids:
        employees = [e for e in employees if e.id in set(employee_ids)]

    ts_rows = {(t.employee_id, t.date): t for t in db.scalars(select(TimesheetRow).where(
        TimesheetRow.date >= first, TimesheetRow.date <= last))}

    # «двойные» дни месяца (производственный календарь + ВИП-периоды) — для маркеров ×2;
    # считается вживую, поэтому актуально даже для будущих дней до пересчёта
    dbl = double_map_for(db, [e.id for e in employees], first, last)

    today = now_local().date()
    result = []
    grand = {"planned": 0.0, "fact": 0.0, "night": 0.0, "day": 0.0, "ot": 0.0,
             "deficit": 0.0, "timeoff": 0.0, "issues": 0, "work_days": 0}

    for emp in employees:
        days = []
        d = first
        while d <= last:
            cur = d
            d += dt.timedelta(days=1)
            row = ts_rows.get((emp.id, cur))
            if row is None:
                continue
            try:
                detail = json.loads(row.detail_json or "{}")
            except json.JSONDecodeError:
                detail = {}
            days.append({
                "date": cur.isoformat(), "day": cur.day, "weekday": WD_SHORT[cur.weekday()],
                "is_weekend": cur.weekday() >= 5, "is_future": cur > today,
                "double_reason": dbl.get((emp.id, cur.isoformat()), ""),
                "is_double": (emp.id, cur.isoformat()) in dbl,
                "shift_code": row.code,
                "shift_name": row.shift_type.name if row.shift_type else "",
                "color": row.shift_type.color if row.shift_type else "#94a3b8",
                "kind": row.shift_type.kind if row.shift_type else "absence",
                "planned_hours": row.planned_hours, "fact_hours": row.fact_hours,
                "day_hours": row.day_hours, "night_hours": row.night_hours,
                "ot_hours": row.ot_hours, "ot_note": row.ot_note or "",
                "deficit_hours": row.deficit_hours, "timeoff_hours": row.timeoff_hours,
                "fact_in": row.fact_in.isoformat(timespec="minutes") if row.fact_in else None,
                "fact_out": row.fact_out.isoformat(timespec="minutes") if row.fact_out else None,
                "status": row.status, "status_title": STATUS_TITLES.get(row.status, row.status),
                "note": row.note,
                "sessions": detail.get("sessions", []),
                "warnings": detail.get("warnings", []),
            })

        opening = bank_as_of(db, emp, first - dt.timedelta(days=1))
        totals = _totals_from_rows(days, opening)
        for k in grand:
            grand[k] = round(grand[k] + totals[k], 2) if isinstance(grand[k], float) else grand[k] + totals[k]
        result.append({
            "employee": {"id": emp.id, "full_name": emp.full_name, "short_name": emp.display_name,
                         "position": emp.position, "department": emp.department.name if emp.department else None,
                         "schedule_group": emp.schedule_group or "", "group_color": emp.group_color or "#6b7280",
                         "opening_balance": emp.balance_hours},
            "days": days,
            "totals": totals,
        })

    return {"year": year, "month": month, "month_name": month_name(month),
            "rows": result, "grand": grand, "status_titles": STATUS_TITLES}


@router.get("")
def get_timesheet(year: int, month: int, employee_id: Optional[int] = None,
                  principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    if not 1 <= month <= 12:
        raise HTTPException(status_code=422, detail="month должен быть 1..12")
    return _build(db, year, month, [employee_id] if employee_id else None)


@router.post("/recalc")
def recalc(payload: RecalcIn, principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Принудительно пересчитать табель (после изменения правил или массовых правок)."""
    first, last = month_bounds(payload.year, payload.month)
    count = recalc_range(db, first, last, employee_ids=payload.employee_ids)
    return {"ok": True, "recalculated_days": count}


# ─────────────────────────────── выгрузки ───────────────────────────────
def _cell_text(day: dict) -> str:
    """Ячейка табеля: «ДЯ 10 ДН 2», код отсутствия или пусто."""
    if day["kind"] != "work":
        return day["shift_code"] or ""
    parts = []
    if day["day_hours"]:
        parts.append(f"ДЯ {day['day_hours']:g}")
    if day["night_hours"]:
        parts.append(f"ДН {day['night_hours']:g}")
    if not parts and day["status"] in ("no_punch", "unclosed"):
        return "НН"
    return " ".join(parts)


@router.get("/csv")
def export_csv(year: int, month: int, mode: str = "internal",
               principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    """Сетка табеля в CSV («;» + BOM).
    mode=internal — факт отработанных часов по дням (внутренняя сверка);
    mode=payroll — нетто-переработки к выплате по дням (то, что вносится в систему учёта зарплаты)."""
    if mode == "payroll":
        return _payroll_csv(db, year, month)
    data = _build(db, year, month)
    first, last = month_bounds(year, month)
    ndays = (last - first).days + 1

    buf = io.StringIO()
    buf.write("\ufeff")
    import csv as _csv
    w = _csv.writer(buf, delimiter=";")
    header = ["ФИО"] + [f"{(first + dt.timedelta(days=i)).day:02d}.{(first + dt.timedelta(days=i)).month:02d}"
                        for i in range(ndays)] + ["ДЯ", "ДН", "Всего", "Перераб.", "Недораб.", "Банк часов"]
    w.writerow(header)
    for r in data["rows"]:
        cells = {d["date"]: _cell_text(d) for d in r["days"]}
        line = [r["employee"]["full_name"]]
        for i in range(ndays):
            line.append(cells.get((first + dt.timedelta(days=i)).isoformat(), ""))
        t = r["totals"]
        line += [t["day"], t["night"], t["fact"], t["ot"], t["deficit"], t["balance"]]
        w.writerow(line)
    g = data["grand"]
    w.writerow(["ИТОГО"] + [""] * ndays + [g["day"], g["night"], g["fact"], g["ot"], g["deficit"], ""])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="tabel_{year}-{month:02d}.csv"'})


def _payroll_csv(db: Session, year: int, month: int):
    import csv as _csv

    from ..deps import month_name  # noqa: F401  (name месяца не нужен, оставлено для совместимости)

    ot = _overtime_data(db, year, month)
    first, last = month_bounds(year, month)
    ndays = (last - first).days + 1
    buf = io.StringIO()
    buf.write("\ufeff")
    w = _csv.writer(buf, delimiter=";")
    w.writerow(["ФИО"] + [f"{(first + dt.timedelta(days=i)).day:02d}.{(first + dt.timedelta(days=i)).month:02d}"
                           for i in range(ndays)] + ["ДЯ", "ДН", "ДЯ2", "ДН2", "Всего часов",
                                                    "Всего к выплате (в одинарных)"])
    for r in ot["rows"]:
        remain = {x["date"]: x for x in r["remain"]}
        line = [r["employee"]["full_name"]]
        for i in range(ndays):
            iso = (first + dt.timedelta(days=i)).isoformat()
            cell = remain.get(iso)
            parts = []
            if cell and cell["dya"]:
                parts.append(f"ДЯ {cell['dya']:g}")
            if cell and cell["dn"]:
                parts.append(f"ДН {cell['dn']:g}")
            if cell and cell.get("dya2"):
                parts.append(f"ДЯ2 {cell['dya2']:g}")
            if cell and cell.get("dn2"):
                parts.append(f"ДН2 {cell['dn2']:g}")
            line.append(" ".join(parts))
        t = r["totals"]
        line += [t["pay_dya"], t["pay_dn"], t["pay_dya2"], t["pay_dn2"],
                 t["pay_hours"], t["pay_total"]]
        w.writerow(line)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition":
                                      f'attachment; filename="payroll_{year}-{month:02d}.csv"'})


@router.get("/pdf")
def export_pdf(year: int, month: int, principal: Principal = Depends(require_manager),
               db: Session = Depends(get_db)):
    """Табель-сводка в PDF: те же колонки, что в окне «Печать» (план, факт, ДЯ, ДН,
    переработки, недоработки, отгулы, банк часов) + строка ИТОГО. Собирается через
    DOCX → PDF (LibreOffice или встроенный движок reportlab); без движка — 501 с подсказкой."""
    from ..grid_docx import pdf_unavailable_detail, timesheet_docx
    from ..pdf_render import docx_to_pdf

    if not 1 <= month <= 12:
        raise HTTPException(status_code=422, detail="month должен быть 1..12")
    data = _build(db, year, month)
    pdf, how = docx_to_pdf(timesheet_docx(data), f"tabel_{year}-{month:02d}.pdf")
    if pdf is None:
        raise HTTPException(status_code=501, detail=pdf_unavailable_detail(how))
    audit(db, principal, "timesheet_pdf", f"{year}-{month:02d}", {"rows": len(data["rows"])})
    db.commit()
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="tabel_{year}-{month:02d}.pdf"'})


@router.get("/xlsx")
def export_xlsx(year: int, month: int, principal: Principal = Depends(require_manager),
                db: Session = Depends(get_db)):
    """
    Итоговый табель в формате Excel: строка на сотрудника, колонка на день,
    в ячейках «ДЯ 10 ДН 2» (дневные и ночные часы), коды отсутствий, итоги справа.
    Второй лист — журнал переработок с описаниями «с кем работал, что делал».
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise HTTPException(status_code=500, detail="Для выгрузки Excel установите openpyxl: pip install openpyxl")

    data = _build(db, year, month)
    first, last = month_bounds(year, month)
    ndays = (last - first).days + 1

    wb = Workbook()
    ws = wb.active
    ws.title = f"Табель {data['month_name']} {year}"

    thin = Side(style="thin", color="D0D7E2")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill = PatternFill("solid", fgColor="E8EEF7")
    weekend_fill = PatternFill("solid", fgColor="F4F6FA")
    title_font = Font(bold=True, size=13)
    head_font = Font(bold=True, size=9)
    center = Alignment(horizontal="center", vertical="center")

    ws["A1"] = f"Табель учёта рабочего времени за {data['month_name']} {year} г. (часы: ДЯ — день, ДН — ночь)"
    ws["A1"].font = title_font
    ws["A2"] = "Учёт кратен часу. Ночная смена относится к дате начала (как в официальном табеле)."
    ws["A2"].font = Font(size=9, italic=True, color="66748A")

    hr = 4
    ws.cell(row=hr, column=1, value="ФИО").font = head_font
    ws.cell(row=hr, column=1).fill = head_fill
    ws.cell(row=hr, column=1).border = border
    for i in range(ndays):
        d = first + dt.timedelta(days=i)
        c = ws.cell(row=hr, column=2 + i, value=f"{d.day:02d}.{d.month:02d}")
        c.font = head_font
        c.fill = head_fill
        c.alignment = center
        c.border = border
        if d.weekday() >= 5:
            c.fill = weekend_fill
    totals_cols = ["ДЯ", "ДН", "Всего", "Перераб.", "Недораб.", "Отгулы", "Банк"]
    for j, name in enumerate(totals_cols):
        c = ws.cell(row=hr, column=2 + ndays + j, value=name)
        c.font = head_font
        c.fill = head_fill
        c.alignment = center
        c.border = border

    row_i = hr + 1
    for r in data["rows"]:
        cells = {d["date"]: d for d in r["days"]}
        name_cell = ws.cell(row=row_i, column=1, value=r["employee"]["full_name"])
        name_cell.border = border
        name_cell.font = Font(size=10)
        for i in range(ndays):
            d = cells.get((first + dt.timedelta(days=i)).isoformat())
            text = _cell_text(d) if d else ""
            c = ws.cell(row=row_i, column=2 + i, value=text)
            c.alignment = center
            c.border = border
            c.font = Font(size=8)
            if (first + dt.timedelta(days=i)).weekday() >= 5:
                c.fill = weekend_fill
            if d and d["ot_hours"]:
                c.font = Font(size=8, color="B45309", bold=True)
            if d and d["status"] in ("no_punch", "unclosed", "work_no_plan"):
                c.font = Font(size=8, color="B91C1C", bold=True)
        t = r["totals"]
        for j, val in enumerate([t["day"], t["night"], t["fact"], t["ot"], t["deficit"], t["timeoff"], t["balance"]]):
            c = ws.cell(row=row_i, column=2 + ndays + j, value=val)
            c.border = border
            c.alignment = center
            c.font = Font(size=9, bold=(j == 2))
        row_i += 1

    g = data["grand"]
    total_row = row_i
    ws.cell(row=total_row, column=1, value="ИТОГО по объекту").font = Font(bold=True, size=10)
    for j, val in enumerate([g["day"], g["night"], g["fact"], g["ot"], g["deficit"], g["timeoff"], ""]):
        c = ws.cell(row=total_row, column=2 + ndays + j, value=val)
        c.font = Font(bold=True, size=9)
        c.alignment = center

    ws.column_dimensions["A"].width = 30
    for i in range(ndays):
        ws.column_dimensions[get_column_letter(2 + i)].width = 9
    for j in range(len(totals_cols)):
        ws.column_dimensions[get_column_letter(2 + ndays + j)].width = 8
    ws.freeze_panes = "B5"

    # лист для внешней системы учёта зарплаты: нетто-переработки по дням
    # (ДЯ2/ДН2 — часы дней двойной оплаты: производственный календарь / ВИП-гости)
    ot = _overtime_data(db, year, month)
    wspay = wb.create_sheet("В учёт зарплаты")
    wspay.append(["ФИО"] + [f"{(first + dt.timedelta(days=i)).day:02d}.{(first + dt.timedelta(days=i)).month:02d}"
                            for i in range(ndays)] + ["ДЯ", "ДН", "ДЯ2", "ДН2", "Всего часов",
                                                     "Всего к выплате (в одинарных)"])
    for c in wspay[1]:
        c.font = head_font; c.fill = head_fill; c.alignment = center
    double_font = Font(size=9, bold=True, color="B45309")
    for r in ot["rows"]:
        remain = {x["date"]: x for x in r["remain"]}
        row_vals = [r["employee"]["full_name"]]
        for i in range(ndays):
            cell = remain.get((first + dt.timedelta(days=i)).isoformat())
            parts = []
            if cell and cell["dya"]:
                parts.append(f"ДЯ {cell['dya']:g}")
            if cell and cell["dn"]:
                parts.append(f"ДН {cell['dn']:g}")
            if cell and cell.get("dya2"):
                parts.append(f"ДЯ2 {cell['dya2']:g}")
            if cell and cell.get("dn2"):
                parts.append(f"ДН2 {cell['dn2']:g}")
            row_vals.append(" ".join(parts))
        t = r["totals"]
        row_vals += [t["pay_dya"], t["pay_dn"], t["pay_dya2"], t["pay_dn2"],
                     t["pay_hours"], t["pay_total"]]
        wspay.append(row_vals)
        if t["pay_dya2"] or t["pay_dn2"]:
            for col in range(len(row_vals) - 3, len(row_vals) - 1):
                wspay.cell(row=wspay.max_row, column=col).font = double_font
    for i in range(ndays):
        wspay.column_dimensions[get_column_letter(2 + i)].width = 9
    for j in range(6):
        wspay.column_dimensions[get_column_letter(2 + ndays + j)].width = 11
    wspay.column_dimensions["A"].width = 30
    wspay.freeze_panes = "B2"

    # лист-памятка: как получен итог (начисления, списания, зачёт)
    wsot = wb.create_sheet("Зачёт переработок")
    wsot.append(["Сотрудник", "Начислено ДЯ", "Начислено ДН", "Начислено ДЯ2", "Начислено ДН2",
                 "Списано (опозд./ранн./отгулы)",
                 "К выплате ДЯ", "К выплате ДН", "К выплате ДЯ2", "К выплате ДН2",
                 "Всего к выплате (в одинарных)"])
    for c in wsot[1]:
        c.font = head_font; c.fill = head_fill
    for r in ot["rows"]:
        t = r["totals"]
        if t["credit_dya"] or t["credit_dn"] or t["credit_dya2"] or t["credit_dn2"] or t["debit"]:
            wsot.append([r["employee"]["full_name"], t["credit_dya"], t["credit_dn"],
                         t["credit_dya2"], t["credit_dn2"], t["debit"],
                         t["pay_dya"], t["pay_dn"], t["pay_dya2"], t["pay_dn2"],
                         t["pay_total"]])
    wsot.append([])
    wsot.append(["Зачёт: списание вычитается сначала из дневных часов самых ранних дней, затем из ночных."])
    wsot.append(["ДЯ2/ДН2 — дни двойной оплаты (производственный календарь, ВИП-гости): двойной тариф."])
    wsot.append(["Списания, ложащиеся на двойные часы, снимают их вполовину: 8 одинарных часов = 4 часа ДЯ2."])
    wsot.append(["Подробный журнал зачёта — в разделе «Табель» → панель «Переработки к выплате» → кнопка «зачёт»."])
    wsot.column_dimensions["A"].width = 30
    for col in "BCDEFGHIJK":
        wsot.column_dimensions[col].width = 16

    # лист переработок с описаниями
    ws2 = wb.create_sheet("Переработки")
    ws2.append(["Дата", "Сотрудник", "Часы переработки", "С кем работал / что делал"])
    for c in ws2[1]:
        c.font = head_font
        c.fill = head_fill
    found = False
    for r in data["rows"]:
        for d in r["days"]:
            if d["ot_hours"] or d["ot_note"]:
                ws2.append([d["date"], r["employee"]["full_name"], d["ot_hours"], d["ot_note"] or ""])
                found = True
    if not found:
        ws2.append(["—", "переработок за месяц нет", "", ""])
    ws2.column_dimensions["A"].width = 12
    ws2.column_dimensions["B"].width = 30
    ws2.column_dimensions["C"].width = 16
    ws2.column_dimensions["D"].width = 70

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="tabel_{year}-{month:02d}.xlsx"'})


def _overtime_data(db: Session, year: int, month: int) -> dict:
    """Реестр переработок к выплате с СКВОЗНЫМ зачётом: непокрытое списание становится долгом
    и гасит переработки следующих месяцев (банк при этом копится отдельно)."""
    first, last = month_bounds(year, month)
    employees = db.scalars(select(Employee).where(
        Employee.active.is_(True), Employee.deleted_at.is_(None))
        .order_by(Employee.schedule_group, Employee.full_name)).all()
    out = []
    for emp in employees:
        rows = db.scalars(select(TimesheetRow).where(
            TimesheetRow.employee_id == emp.id, TimesheetRow.date <= last).order_by(TimesheetRow.date)).all()
        credits, debits = [], []
        for t in rows:
            iso = t.date.isoformat()
            if t.pay_ot_day or t.pay_ot_night or t.pay_ot_day2 or t.pay_ot_night2:
                credits.append({"date": iso, "dya": t.pay_ot_day, "dn": t.pay_ot_night,
                                "dya2": t.pay_ot_day2, "dn2": t.pay_ot_night2,
                                "double": bool(t.pay_ot_day2 or t.pay_ot_night2)})
            if t.unused_hours:
                debits.append({"date": iso, "hours": t.unused_hours,
                               "kind": "Не отработано в официальном окне (опоздание/ранний уход)"})
            if t.timeoff_hours:
                debits.append({"date": iso, "hours": t.timeoff_hours, "kind": "Выходной за часы"})
        prefix_c = [c for c in credits if c["date"] < first.isoformat()]
        prefix_d = [d for d in debits if d["date"] < first.isoformat()]
        _, _, pre_totals = settle_overtime(prefix_c, prefix_d)
        carry_in = pre_totals["debt_out"]
        log, remain, totals = settle_overtime(credits, debits, carry_in=carry_in)
        remain_month = [r for r in remain if first.isoformat() <= r["date"] <= last.isoformat()]
        month_credits = [c for c in credits if c["date"] >= first.isoformat()]
        month_debits = [d for d in debits if d["date"] >= first.isoformat()]
        out.append({
            "employee": {"id": emp.id, "full_name": emp.full_name,
                         "short_name": emp.display_name, "position": emp.position},
            "credits": month_credits, "debits": month_debits,
            # фильтр был «… or True», то есть не отфильтровывал ничего: отдаём журнал целиком
            "log": list(log),
            "remain": remain_month,
            "carry_in": carry_in, "carry_out": totals["debt_out"],
            "totals": {
                "credit_dya": round(sum(c["dya"] for c in month_credits), 2),
                "credit_dn": round(sum(c["dn"] for c in month_credits), 2),
                "credit_dya2": round(sum(c.get("dya2", 0.0) for c in month_credits), 2),
                "credit_dn2": round(sum(c.get("dn2", 0.0) for c in month_credits), 2),
                "debit": round(sum(d["hours"] for d in month_debits), 2),
                "pay_dya": round(sum(r["dya"] for r in remain_month), 2),
                "pay_dn": round(sum(r["dn"] for r in remain_month), 2),
                "pay_dya2": round(sum(r.get("dya2", 0.0) for r in remain_month), 2),
                "pay_dn2": round(sum(r.get("dn2", 0.0) for r in remain_month), 2),
                "pay_hours": round(sum(r["dya"] + r["dn"] + r.get("dya2", 0.0)
                                       + r.get("dn2", 0.0) for r in remain_month), 2),
                # «Всего к выплате» — в одинарных часах: ДЯ2/ДН2 считаются как два
                "pay_total": round(sum(r["dya"] + r["dn"] + 2.0 * (r.get("dya2", 0.0)
                                       + r.get("dn2", 0.0)) for r in remain_month), 2),
                "carry_in": carry_in, "carry_out": totals["debt_out"],
            },
        })
    return {"year": year, "month": month, "rows": out}


@router.get("/overtime")
def get_overtime(year: int, month: int, principal: Principal = Depends(require_manager),
                 db: Session = Depends(get_db)):
    """Переработки к выплате: начислено (ДЯ/ДН), списано (опоздания/ранние уходы/отгулы),
    зачёт списаний (сначала дневные часы ранних дней) и итог к подаче."""
    return _overtime_data(db, year, month)


@router.get("/audit")
def audit_log(limit: int = 100, principal: Principal = Depends(require_manager), db: Session = Depends(get_db)):
    from ..models import AuditLog

    logs = db.scalars(select(AuditLog).order_by(AuditLog.ts.desc()).limit(min(limit, 500))).all()
    return [{"id": row.id, "ts": row.ts.isoformat(timespec="minutes"), "actor": row.actor_name,
             "action": row.action, "target": row.target, "payload": row.payload_json}
            for row in logs]
