"""Управленческий табель (УТ): режимы view / close, закрытие периода и пересчёт (спец. 7)."""
from __future__ import annotations

import datetime as dt
import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import Principal, audit
from ..db import get_db
from ..engine.adapters.bulk import build_bulk_ports
from ..engine.adapters.factory import build_ports
from ..engine.adapters.sql_schedule import ScheduleCache
from ..engine.application.close_period import close_period
from ..engine.application.errors import ApplicationError
from ..engine.application.periods import month_period
from ..engine.application.recalculate import recalculate
from ..engine.application.view_period import preview_close, view_period
from ..engine.domain.time.local_midnight import local_midnight
from ..engine.domain.types.errors import DomainError
from ..engine.interface.serialize import plain
from ..engine.interface.views import period_view_dict, result_view
from ..permissions import principal_permissions, require_perm
from .engine_common import domain_error_text, emp_brief, period_employees

router = APIRouter(prefix="/api/mgmt", tags=["mgmt-timesheet"])


def _ports(db: Session, principal: Optional[Principal], emp_ids: list[int], period, cache=None):
    """Порты для чтения группы сотрудников — пакетная предзагрузка (без N+1)."""
    return build_bulk_ports(db, emp_ids, period.start, period.end, principal.name if principal else "")


def _write_ports(db: Session, principal: Optional[Principal], emp_id: int, period):
    cache = ScheduleCache(db)
    cache.preload([emp_id], period.start - dt.timedelta(days=1), period.end)
    return build_ports(db, principal.name if principal else "", cache=cache)


def _row(db, ports, emp, period, mode, detail=False) -> dict:
    eid = str(emp.id)
    st = ports.settings.load(period)
    store = ports.store
    state = store.period_state(eid, period)
    base = {"employee": emp_brief(emp), "closed": state.closed, "next_closed": state.next_closed,
            "mode": mode, "error": None}
    try:
        if mode == "close" and state.closed:
            saved = store.load_result(eid, period)
            flags = plain(view_period(eid, period, ports).flags.flags)
            return {**base, **result_view(saved["result"], flags, st.tz, detail), "source": "saved",
                    "revision": saved["revision"], "closed_by": saved["closed_by"], "closed_at": saved["closed_at"]}
        view = preview_close(eid, period, ports) if mode == "close" else view_period(eid, period, ports)
        return {**base, **period_view_dict(view, st.tz, detail), "source": "preview" if mode == "close" else "view"}
    except (DomainError, ApplicationError, ValueError) as exc:
        return {**base, "error": domain_error_text(exc)}


@router.get("")
def get_mgmt(year: int, month: int, mode: str = "view", principal: Principal = Depends(require_perm("mgmt.view")),
             db: Session = Depends(get_db)):
    if mode not in ("view", "close"):
        raise HTTPException(status_code=422, detail="mode: view | close")
    period = month_period(year, month)
    emps = period_employees(db, period.start, period.end)
    ports = _ports(db, principal, [e.id for e in emps], period)
    st = ports.settings.load(period)
    now = ports.clock.now()
    complete = now >= local_midnight(period.end + dt.timedelta(days=1), st.tz)
    rows = [_row(db, ports, e, period, mode) for e in emps]
    perms = principal_permissions(db, principal)
    return {"year": year, "month": month, "mode": mode, "complete": complete,
            "period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
            "days": [(period.start + dt.timedelta(days=i)).isoformat() for i in range((period.end - period.start).days + 1)],
            "tariffs": list(st.placement.tariff_order), "step_minutes": st.step_minutes,
            "settings_versions": list(st.versions),
            "can_close": "mgmt.close" in perms, "can_recalculate": "mgmt.recalculate" in perms,
            "rows": rows}


@router.get("/employee/{employee_id}")
def get_detail(employee_id: int, year: int, month: int, mode: str = "view",
               principal: Principal = Depends(require_perm("mgmt.view")), db: Session = Depends(get_db)):
    period = month_period(year, month)
    emps = period_employees(db, period.start, period.end, [employee_id])
    if not emps:
        raise HTTPException(status_code=404, detail="Сотрудник не работал в этом периоде")
    ports = _ports(db, principal, [employee_id], period)
    return _row(db, ports, emps[0], period, mode, detail=True)


class PeriodAction(BaseModel):
    year: int
    month: int
    employee_ids: Optional[list[int]] = None


def _run_action(payload: PeriodAction, principal: Principal, db: Session, action) -> dict:
    period = month_period(payload.year, payload.month)
    emps = period_employees(db, period.start, period.end, payload.employee_ids)
    done, errors = [], []
    for emp in emps:
        ports = _write_ports(db, principal, emp.id, period)
        try:
            view = action(str(emp.id), period, ports)
            done.append({"employee_id": emp.id, "bank_closed": round(view.settle.bank_closed_minutes / 60, 2),
                         "deferred": len(view.settle.deferred_blocks)})
        except (DomainError, ApplicationError, ValueError) as exc:
            db.rollback()
            errors.append({"employee_id": emp.id, "name": emp.display_name, "error": domain_error_text(exc)})
    return {"period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
            "done": done, "errors": errors}


@router.post("/close")
def close(payload: PeriodAction, principal: Principal = Depends(require_perm("mgmt.close")),
          db: Session = Depends(get_db)):
    """close_period по каждому сотруднику: отдельная атомарная транзакция на сотрудника."""
    out = _run_action(payload, principal, db, close_period)
    audit(db, principal, "period_close", f"{payload.year}-{payload.month:02d}",
          {"employees": [d["employee_id"] for d in out["done"]], "errors": out["errors"]})
    db.commit()
    return out


@router.post("/recalculate")
def recalc(payload: PeriodAction, principal: Principal = Depends(require_perm("mgmt.recalculate")),
           db: Session = Depends(get_db)):
    out = _run_action(payload, principal, db, recalculate)
    audit(db, principal, "period_recalculate", f"{payload.year}-{payload.month:02d}",
          {"employees": [d["employee_id"] for d in out["done"]], "errors": out["errors"]})
    db.commit()
    return out


@router.get("/xlsx")
def export_xlsx(year: int, month: int, mode: str = "view", principal: Principal = Depends(require_perm("mgmt.view")),
                db: Session = Depends(get_db)):
    """УТ в Excel: «ФИО × дни», ячейка «ДЯ 10 ДН 2», итоги по кодам и банк."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    data = get_mgmt(year, month, mode, principal, db)
    wb = Workbook()
    ws = wb.active
    ws.title = f"УТ {month:02d}.{year}"
    days = data["days"]
    tariffs = data["tariffs"]
    ws.append(["ФИО", "Табельный №"] + [d[8:] for d in days] + tariffs + ["Недостача", "Банк на закрытие", "Статус"])
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in data["rows"]:
        if r.get("error"):
            ws.append([r["employee"]["full_name"], r["employee"]["tab_number"], r["error"]])
            continue
        cells = [" ".join(f"{t} {h:g}" for t, h in r["ut"].get(d, {}).items()) for d in days]
        ws.append([r["employee"]["full_name"], r["employee"]["tab_number"], *cells,
                   *[r["totals"].get(t, 0) for t in tariffs], r["debt"]["residual"], r["bank"]["closed"],
                   "закрыт" if r["closed"] else ("предпросмотр закрытия" if r.get("source") == "preview" else "просмотр")])
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 34
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    name = f"upr_tabel_{year}_{month:02d}_{mode}.xlsx"
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


def json_dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)
