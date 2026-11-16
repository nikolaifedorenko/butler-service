"""Вкладка «Управленческий табель» (16.6): единственный сценарий тяжёлого конвейера.

Период — календарный месяц либо половина месяца по настройке period_granularity
(v7.1/R36). Открытие: месяц не закрыт → view_period (живой расчёт, ничего не
сохраняется; при незакрытом предыдущем — типизированное отклонение); закрыт → чтение
сохранённых SettleResult и снимка FlagsResult без пересчёта. «Закрыть месяц» →
close_period; «Пересчитать» → recalculate (только последний закрытый период).
Периоды вне трудоустройства не предлагаются и показываются отказом (R35).

Закрытие и пересчёт — «всё или ничего» по всему штату периода (решение владельца
25.10.2026): сначала предпроверка каждого (тот же расчёт, без записи); хоть одна
ошибка — не трогаем никого и отдаём полный список. Выбрать сотрудников нельзя."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import transaction
from app.core.errors import Conflict, NotFound
from app.core.permissions import principal_permissions
from app.modules.exchange.application.tables import write_xlsx

from ..domain.settings.types import GRANULARITY_HALF_MONTH
from ..domain.time.local_midnight import next_midnight
from ..domain.types.entities import Employment, Period
from ..domain.types.errors import DomainError
from . import exports
from .close_period import check_close, close_period
from .engine_common import emp_brief, engine_ports, now_utc, period_employees
from .errors import ApplicationError
from .months import half_month_period, month_period
from .period_params import ensure_period
from .recalculate import check_recalculate, recalculate
from .texts import error_text
from .view_period import view_period
from .views import period_view_dict


def _period(payload_year: int, payload_month: int, half: Optional[int], granularity: str) -> Period:
    if granularity == GRANULARITY_HALF_MONTH:
        return half_month_period(payload_year, payload_month, 2 if half == 2 else 1)
    return month_period(payload_year, payload_month)


# ключи строки сотрудника: у строки с отказом расчёта заполнены только employee и error
_ROW_KEYS = ("revision", "closed_by", "closed_at", "versions", "effective_period", "employment",
             "out_of_staff_days", "days", "ut", "bank", "debt", "deferred", "exceptions", "cuts", "totals",
             "trace", "state", "source")
_NOT_SAVED = {"revision": None, "closed_by": None, "closed_at": None, "versions": None}


def _row(db: Session, ports, emp, period: Period, now: dt.datetime, detail: bool) -> dict:
    eid = str(emp.id)
    base = {**dict.fromkeys(_ROW_KEYS), "employee": emp_brief(emp), "error": None}
    try:
        state = ports.store.period_state(eid, period)
        view = view_period(eid, period, now, ports)
        employment = view.employment
        effective_end = _effective_end(period, employment)
        can_close_now = now >= next_midnight(effective_end, ports.settings.load(period).tz)
        meta = (ports.store.saved_meta(eid, period)
                if state.closed and hasattr(ports.store, "saved_meta") else {}) or {}
        return {**base, **_NOT_SAVED, **meta,
                **period_view_dict(view, period, detail=detail),
                "state": {"closed": state.closed, "previous_closed": state.previous_closed,
                          "next_closed": state.next_closed,
                          "opening_bank_set": state.opening_bank_set,
                          "can_close": (not state.closed)
                          and (state.previous_closed or state.opening_bank_set) and can_close_now,
                          "can_recalculate": state.closed and not state.next_closed},
                "source": "saved" if state.closed else "view"}
    except (DomainError, ApplicationError, ValueError) as exc:
        # отказ расчёта — не ошибка запроса: текст идёт в строку сотрудника
        return {**base, "error": error_text(exc)}


def _effective_end(period: Period, employment: Employment) -> dt.date:
    return period.end if employment.end is None else min(period.end, employment.end)


def _context(db: Session, principal: Optional[Principal], year: int, month: int,
             half: Optional[int], ids: Optional[list[int]]):
    """Контекст вкладки: порты, гранулярность, период, сотрудники.

    Повреждённые настройки — отказ 409 с человеческим текстом: вкладка должна показать,
    что именно сломано и где это чинить.
    """
    ensure_period(year, month)
    now = now_utc()
    ports = engine_ports(db, principal, now)
    try:
        granularity = ports.settings.load(month_period(year, month)).period_granularity
    except ValueError as exc:
        raise Conflict(str(exc)) from exc
    period = _period(year, month, half, granularity)
    emps = period_employees(db, period.start, period.end, ids)
    return now, ports, granularity, period, emps


def table(db: Session, principal: Principal, year: int, month: int, half: Optional[int] = None,
          employee_id: Optional[int] = None, detail: bool = False) -> dict:
    """Управленческий табель периода: по строке на сотрудника."""
    now, ports, granularity, period, emps = _context(db, principal, year, month, half,
                                                     [employee_id] if employee_id else None)
    if employee_id and not emps:
        raise NotFound("Сотрудник не трудоустроен в этом периоде")
    try:
        st = ports.settings.load(period)
    except ValueError as exc:
        raise Conflict(str(exc)) from exc
    rows = [_row(db, ports, e, period, now, detail or bool(employee_id)) for e in emps]
    perms = principal_permissions(db, principal)
    return {"year": year, "month": month, "half": half, "granularity": granularity,
            "period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
            "days": [(period.start + dt.timedelta(days=i)).isoformat()
                     for i in range((period.end - period.start).days + 1)],
            "tariffs": list(st.placement_order), "step_minutes": st.step_minutes,
            "settings_versions": list(st.versions), "now": now.isoformat(),
            "can_close": "mgmt.close" in perms, "can_recalculate": "mgmt.recalculate" in perms,
            "rows": rows}


class PeriodAction(BaseModel):
    # без employee_ids: период закрывается и пересчитывается только у всего штата.
    # Лишние поля — 422, а не молча игнорируются: иначе старый клиент, приславший
    # employee_ids, закрыл бы период всем, думая, что закрывает одному
    model_config = ConfigDict(extra="forbid")

    year: int
    month: int
    half: Optional[int] = None


def _error_row(emp, exc: Exception) -> dict:
    return {"employee_id": emp.id, "name": emp.display_name, "error": error_text(exc)}


def _run_all(db: Session, principal: Principal, payload: PeriodAction, check, action,
             audit_action: str, *, skip_closed: bool) -> dict:
    """Предпроверка всех → действие для всех. skip_closed (закрытие): у кого период уже
    закрыт — пропускаем; так докрывается период, закрытый частично прежними правилами
    или прерванный сбоем."""
    now, ports, _granularity, period, emps = _context(db, principal, payload.year, payload.month,
                                                      payload.half, None)
    out = {"period": {"start": period.start.isoformat(), "end": period.end.isoformat()},
           "total": len(emps), "skipped_closed": 0, "stage": "check", "done": [], "errors": []}
    todo = []
    for emp in emps:
        if skip_closed and ports.store.period_state(str(emp.id), period).closed:
            out["skipped_closed"] += 1
            continue
        try:
            check(str(emp.id), period, now, ports)
            todo.append(emp)
        except (DomainError, ApplicationError, ValueError) as exc:
            out["errors"].append(_error_row(emp, exc))
    db.rollback()       # предпроверка только читала — снимок сессии не нужен
    if not out["errors"]:
        _save_all(db, principal, period, now, ports, todo, action, audit_action, out)
    out = {**out, "ok": not out["errors"]}
    # итог операции — отдельной записью журнала: закрытия сотрудников уже зафиксированы
    with transaction(db):
        audit(db, principal, audit_action, f"{payload.year}-{payload.month:02d}",
              {"employees": [d["employee_id"] for d in out["done"]], "stage": out["stage"],
               "errors": out["errors"]})
    return out


def _save_all(db: Session, principal: Principal, period: Period, now: dt.datetime, ports, todo: list,
              action, audit_action: str, out: dict) -> None:
    """Действие для каждого сотрудника — своей транзакцией (UnitOfWork внутри use case)."""
    out["stage"] = "save"
    for emp in todo:
        # у каждого сотрудника своя транзакция (UnitOfWork внутри use case); запись
        # аудита кладём в сессию ДО неё — UoW закоммитит её вместе с закрытием (ARCH-01)
        audit(db, principal, audit_action, f"employee:{emp.id}",
              {"period": f"{period.start.isoformat()}..{period.end.isoformat()}"})
        try:
            view = action(str(emp.id), period, now, ports)
            out["done"].append({"employee_id": emp.id,
                                "bank_closed": round(view.settle.bank_closed_minutes / 60, 2),
                                "deferred": len(view.settle.deferred_blocks)})
        except (DomainError, ApplicationError, ValueError) as exc:
            # редкость: правка между предпроверкой и записью; повторное «Закрыть» докроет
            db.rollback()
            out["errors"].append(_error_row(emp, exc))


def close(db: Session, principal: Principal, payload: PeriodAction) -> dict:
    """Закрыть период у всего штата; у кого он уже закрыт — пропустить."""
    return _run_all(db, principal, payload, check_close, close_period, "period_close", skip_closed=True)


def recalc(db: Session, principal: Principal, payload: PeriodAction) -> dict:
    """Пересчитать последний закрытый период у всего штата."""
    return _run_all(db, principal, payload, check_recalculate, recalculate, "period_recalculate",
                    skip_closed=False)


def export_xlsx(db: Session, principal: Principal, year: int, month: int,
                half: Optional[int] = None) -> tuple[bytes, str]:
    """УТ в Excel — форма ``exports.mgmt_sheet``. Возвращает (файл, имя файла)."""
    data = table(db, principal, year, month, half)
    name = f"upr_tabel_{year}_{month:02d}{'_h' + str(half) if half else ''}.xlsx"
    return write_xlsx([exports.mgmt_sheet(data, year, month)]), name
