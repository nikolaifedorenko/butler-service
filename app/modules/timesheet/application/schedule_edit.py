"""Правки Графика (16.3): ручная смена дня, согласованное отсутствие, отсутствие на период,
сброс месяца.

Правка Графика не меняет часы (RUL-SCHEDULE-ONLY-FLAGS). Каждая операция — одна транзакция
с записью в журнал; массовые правки записываются целиком либо не записываются вовсе."""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.auth import Principal
from app.core.db import lock_employee, transactional
from app.core.errors import NotFound, Validation
from app.core.time import TZ
from app.modules.people.application import Employee, employed_on, periods_of

from ..adapters.orm import ScheduleAbsence, ScheduleShift, ShiftType, TabelDay
from ..domain.types.entities import Shift
from ..domain.types.errors import DomainError
from . import schedule_view, timesheet_edit
from .bulk import NothingWritten, all_or_nothing
from .engine_common import engine_ports, now_utc
from .errors import ApplicationError
from .months import month_period
from .period_params import ensure_period
from .schedule_grid import month_bounds, month_bounds_utc, period_settings, visible_employees
from .schedule_view import rebuild_generated_for_days
from .texts import error_text, fmt_hours_strict

_HHMM = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def _to_utc(day: dt.date, hhmm: str, next_day: bool = False) -> dt.datetime:
    hh, mm = (int(x) for x in hhmm.split(":"))
    local = dt.datetime.combine(day + (dt.timedelta(days=1) if next_day else dt.timedelta()),
                                dt.time(hh, mm), TZ)
    return local.astimezone(dt.UTC)


class ShiftIntervalIn(BaseModel):
    start: str                       # "HH:MM"
    end: str                         # "HH:MM"
    end_next_day: bool = False
    note: str = ""


class ManualShiftIn(BaseModel):
    employee_id: int
    date: dt.date
    shifts: list[ShiftIntervalIn]
    shift_type_id: Optional[int] = None     # пресет из словаря (время берётся из него)


@transactional
def put_manual_shift(db: Session, principal: Principal, payload: ManualShiftIn) -> None:
    """Ручная смена дня: заменяет генерацию дня целиком. Интервалы — из запроса либо из
    словарной смены."""
    intervals = payload.shifts
    if payload.shift_type_id is not None and not intervals:
        kind = db.get(ShiftType, payload.shift_type_id)
        if kind is None or kind.kind != "work":
            raise Validation("Смена словаря не найдена")
        intervals = [ShiftIntervalIn(start=kind.start_time, end=kind.end_time,
                                     end_next_day=bool(kind.overnight))]
    if not intervals:
        raise Validation("Укажите интервалы смены")
    shifts = []
    for iv in intervals:
        if not (_HHMM.match(iv.start) and _HHMM.match(iv.end)):
            raise Validation("Время в формате ЧЧ:ММ")
        start = _to_utc(payload.date, iv.start)
        end = _to_utc(payload.date, iv.end, iv.end_next_day)
        if end <= start:
            raise Validation("Конец смены должен быть позже начала (или отметьте "
                             "«заканчивается на следующие сутки»)")
        shifts.append(Shift(str(payload.employee_id), start, end))
    ports = engine_ports(db, principal, now_utc())
    try:
        schedule_view.save_schedule_day(str(payload.employee_id), payload.date, shifts, ports)
    except (DomainError, ApplicationError) as exc:
        # Проверки записи Графика (CHK-SHIFT-*) и редактируемость дня — ошибка ВВОДА: 422.
        # Общий перевод ошибок расчёта в 409 («настройки повреждены») здесь не подходит.
        raise Validation(error_text(exc)) from exc
    for row, iv in zip(db.scalars(select(ScheduleShift).where(
            ScheduleShift.employee_id == payload.employee_id,
            ScheduleShift.date == payload.date, ScheduleShift.source == "manual")
            # ORDER BY обязателен: zip расставляет ноты по интервалам запроса, а без
            # порядка БД строки возвращаются как угодно (PostgreSQL порядок не
            # гарантирует) — ноты ложились бы на чужие смены (ревью 20.10.2026,
            # P1-ts-2). id назначаются в порядке вставки одним flush в save_manual,
            # т.е. порядок id = порядок intervals (start не годится: интервалы
            # запроса могут быть вне хронологии).
            .order_by(ScheduleShift.id)),
                     intervals, strict=False):
        row.note = iv.note[:255]
        row.updated_by = principal.user.id
    audit(db, principal, "schedule_manual_shift", f"employee:{payload.employee_id}",
          {"date": payload.date.isoformat(),
           "shifts": [[i.start, i.end, i.end_next_day] for i in intervals]})


@transactional
def delete_manual_shift(db: Session, principal: Principal, employee_id: int, date: dt.date) -> None:
    """Удаление ручной смены — день возвращается к генерации из Табеля (16.3)."""
    ports = engine_ports(db, principal, now_utc())
    schedule_view.drop_manual_day(str(employee_id), date, ports)
    # генерация дня была вытеснена ручной сменой при сохранении — восстанавливаем
    schedule_view.rebuild_generated_schedule(str(employee_id),
                                             month_period(date.year, date.month), ports)
    audit(db, principal, "schedule_drop_manual", f"employee:{employee_id}",
          {"date": date.isoformat()})


class AbsenceIn(BaseModel):
    employee_id: int
    date: dt.date
    from_time: str                   # "HH:MM"
    until_time: str                  # "HH:MM"
    next_day: bool = False
    kind_id: Optional[int] = None    # тип отсутствия из словаря (заявление, режим отметок)
    note: str = ""
    doc_type: str = ""               # шаблон заявления (18.10.2026): пусто — по точке ввода


@transactional
def add_absence(db: Session, principal: Principal, payload: AbsenceIn) -> int:
    """«Пропуск/отлучка» — согласованное отсутствие (логический разрез Графика, v7/R17).
    На часы и банк не влияет (RUL-ABSENCE-ONLY-FLAGS): недостача возникает из отсутствия
    присутствия в окне и гасится банком/кодами по периоду. Возвращает номер записи."""
    for value in (payload.from_time, payload.until_time):
        if not _HHMM.match(value or ""):
            raise Validation("Время в формате ЧЧ:ММ")
    if db.get(Employee, payload.employee_id) is None:
        raise NotFound("Сотрудник не найден")
    ports = engine_ports(db, principal, now_utc())
    try:
        absence_id = schedule_view.save_absence(str(payload.employee_id), payload.date,
                                                payload.from_time, payload.until_time,
                                                payload.next_day, ports)
    except (DomainError, ApplicationError) as exc:
        # проверки записи отсутствия (CHK-ABSENCE-ORDER/LENGTH) — ошибка ВВОДА: 422
        raise Validation(error_text(exc)) from exc
    row = db.get(ScheduleAbsence, absence_id)
    if row is not None:
        row.kind_id = payload.kind_id
        row.note = payload.note[:255]
        row.created_by = principal.user.id
        # выбранный в диалоге шаблон заявления (18.10.2026): пусто — правило
        # по точке входа (вся смена / интервал) из doc_type_of_absence
        row.doc_type = (payload.doc_type or "").strip()[:40]
    audit(db, principal, "schedule_absence", f"employee:{payload.employee_id}",
          {"date": payload.date.isoformat(), "from": payload.from_time,
           "until": payload.until_time, "next_day": payload.next_day,
           "kind_id": payload.kind_id})
    return absence_id


@transactional
def remove_absence(db: Session, principal: Principal, absence_id: int) -> None:
    ports = engine_ports(db, principal, now_utc())
    schedule_view.drop_absence(absence_id, ports)
    audit(db, principal, "schedule_absence_remove", f"absence:{absence_id}", {})


# ── отсутствие на период: коды Табеля (первичный документ) ────────────────────

class RangeAbsenceIn(BaseModel):
    employee_ids: list[int]
    first: dt.date
    last: dt.date
    shift_type_id: Optional[int] = None   # вид отсутствия из словаря (код — из его Т-13)
    code: str = ""                        # либо код Табеля напрямую (ОТ/ДО/Б/ОВ/НН…)
    note: str = ""
    workdays_only: bool = False           # только дни, где по Табелю была работа


def day_window_hhmm(db: Session, st, employee_id: int, day: dt.date) -> tuple[str, str, bool]:
    """Интервал согласованного отсутствия на день: окно значения Табеля, иначе сутки.

    Отсутствие покрывает смену целиком — так в Табеле остаётся явка, отсутствие снимает
    ожидание и флаги, а недостачу гасит банк (паттерн EX-29).
    """
    row = db.scalar(select(TabelDay).where(TabelDay.employee_id == employee_id,
                                           TabelDay.date == day))
    if row is not None:
        policy = st.day_code_policy.get(row.code)
        if policy is not None and policy.carries_hours:
            value = (f"{row.code} {fmt_hours_strict(row.plan_minutes, row.employee_id, row.date)}"
                     if row.plan_minutes else row.code)
            window = st.windows.get(value)
            if window is not None:
                # окно до полуночи (end_minute = 1440, CHK-WINDOW-BOUNDS) — «00:00 следующих
                # суток»: «24:00» роняло dt.time ValueError'ом → 500 (рецензия аудита 22.10.2026)
                end_next_day = window.end_minute == 1440
                end = 0 if end_next_day else window.end_minute
                return (f"{window.start_minute // 60:02d}:{window.start_minute % 60:02d}",
                        f"{end // 60:02d}:{end % 60:02d}", end_next_day)
    return "00:00", "00:00", True


def _range_absence_as_schedule(db: Session, principal: Principal, payload: RangeAbsenceIn,
                               kind: ShiftType) -> dict:
    """Вид отсутствия БЕЗ кода Табеля: пишем согласованные отсутствия в График.

    Норматив от 12.10.2026: «выходной за ранее отработанные часы» и «отпросился» —
    данные Графика, а не код первичного документа. В Табеле остаётся явка («Я»/«К»),
    отсутствие не меняет план (RUL-ABSENCE-ONLY-FLAGS), недостачу гасит банк часов —
    то есть ранее накопленные переработки (EX-29).
    """
    st = period_settings(db, month_period(payload.first.year, payload.first.month))
    ports = engine_ports(db, principal, now_utc())
    written, skipped, errors = 0, 0, []
    for employee_id in payload.employee_ids:
        periods = periods_of(db, employee_id)
        day = payload.first
        while day <= payload.last:
            if not employed_on(periods, day):
                skipped += 1
                day += dt.timedelta(days=1)
                continue
            trow = db.scalar(select(TabelDay).where(TabelDay.employee_id == employee_id,
                                                    TabelDay.date == day))
            carries = bool(trow is not None and st.day_code_policy.get(trow.code)
                           and st.day_code_policy[trow.code].carries_hours)
            if payload.workdays_only and not carries:
                skipped += 1
                day += dt.timedelta(days=1)
                continue
            start_hhmm, end_hhmm, next_day = day_window_hhmm(db, st, employee_id, day)
            try:
                absence_id = schedule_view.save_absence(str(employee_id), day, start_hhmm,
                                                        end_hhmm, next_day, ports)
            except (DomainError, ApplicationError) as exc:
                # отказ дня — не ошибка запроса: он попадает в перечень отказов ответа
                errors.append({"employee_id": employee_id, "date": day.isoformat(),
                               "error": error_text(exc)})
                day += dt.timedelta(days=1)
                continue
            row = db.get(ScheduleAbsence, absence_id)
            if row is not None:
                row.kind_id = kind.id
                row.note = payload.note[:255]
                row.created_by = principal.user.id
            written += 1
            day += dt.timedelta(days=1)
    if errors:
        raise NothingWritten({"ok": False, "written": 0, "skipped": skipped, "errors": errors,
                              "mode": "schedule_absence"})
    audit(db, principal, "schedule_range_absence", f"{payload.first}..{payload.last}",
          {"employees": payload.employee_ids, "kind": kind.code, "written": written,
           "mode": "schedule_absence"})
    return {"ok": True, "written": written, "skipped": skipped, "errors": [],
            "mode": "schedule_absence"}


def range_absence(db: Session, principal: Principal, payload: RangeAbsenceIn) -> dict:
    """«Назначить отсутствие» на период.

    Два способа — по виду отсутствия из словаря:

    * **есть код Табеля** (ОТ, ДО, Б, ОВ, НН…) — отсутствие на весь день это код
      первичного документа; График дня перегенерируется (смены в эти дни нет →
      сотрудник не ожидается, флагов нет);
    * **кода Табеля нет** («Выходной за часы», «Отпросился») — пишется согласованное
      отсутствие в График, Табель не трогается: явка остаётся, недостачу гасит банк
      (норматив от 12.10.2026, паттерн EX-29).

    Период может пересекать границы месяцев.
    """
    if payload.last < payload.first:
        raise Validation("Дата окончания раньше даты начала")
    if (payload.last - payload.first).days > 366:
        raise Validation("Период отсутствия не может быть больше 366 дней")
    if len(payload.employee_ids) > 500:
        raise Validation("Слишком много сотрудников (максимум 500)")
    code = payload.code.strip()
    kind = db.get(ShiftType, payload.shift_type_id) if payload.shift_type_id else None
    if payload.shift_type_id and kind is None:
        raise Validation("Вид отсутствия не найден")
    if not code and kind is not None:
        # вид без кода Табеля — «отпросился (выходной за часы)»: согласованное
        # отсутствие в График, Табель не трогается (норматив 12.10.2026, EX-29)
        return all_or_nothing(db, lambda: _range_absence_as_schedule(db, principal, payload, kind))
    st = period_settings(db, month_period(payload.first.year, payload.first.month))
    policy = st.day_code_policy.get(code)
    if policy is None:
        raise Validation(f"Код «{code or '—'}» отсутствует в CFG-DAY-CODES "
                         "(у вида отсутствия не задан код Т-13)")
    if policy.carries_hours:
        raise Validation("Код несёт плановые часы — это не отсутствие")
    return all_or_nothing(db, lambda: _range_absence_as_code(db, principal, payload, code, st))


def _range_absence_as_code(db: Session, principal: Principal, payload: RangeAbsenceIn, code: str,
                           st) -> dict:
    """Отсутствие кодом Табеля на каждый день периода; График затронутых месяцев — заново."""
    ports = engine_ports(db, principal, now_utc())
    written, skipped, errors = 0, 0, []
    # дни, которые ДЕЙСТВИТЕЛЬНО записаны: График перегенерируется один раз на
    # затронутый месяц после цикла, а не на каждую ячейку (P0-3 ревью 20.10.2026 —
    # на пределе 500×366 по-ячеечная перегенерация давала сотни тысяч запросов)
    touched: dict[int, list[dt.date]] = {}
    for employee_id in payload.employee_ids:
        periods = periods_of(db, employee_id)
        day = payload.first
        while day <= payload.last:
            if not employed_on(periods, day):
                skipped += 1
                day += dt.timedelta(days=1)
                continue
            if payload.workdays_only:
                trow = db.scalar(select(TabelDay).where(TabelDay.employee_id == employee_id,
                                                        TabelDay.date == day))
                carries = (trow is not None and st.day_code_policy.get(trow.code)
                           and st.day_code_policy[trow.code].carries_hours)
                if not carries:
                    skipped += 1
                    day += dt.timedelta(days=1)
                    continue
            try:
                timesheet_edit.save_timesheet_day(str(employee_id), day, code, None, ports,
                                                  rebuild=False)
                row = db.scalar(select(TabelDay).where(TabelDay.employee_id == employee_id,
                                                       TabelDay.date == day))
                if row is not None and payload.note:
                    row.note = payload.note[:255]
                written += 1
                touched.setdefault(employee_id, []).append(day)
            except (DomainError, ApplicationError) as exc:
                # отказ дня — не ошибка запроса: он попадает в перечень отказов ответа
                errors.append({"employee_id": employee_id, "date": day.isoformat(),
                               "error": error_text(exc)})
            day += dt.timedelta(days=1)
    if errors:
        # хоть один день не записался — не пишем ни одного и отдаём полный список: иначе
        # отсутствие оставалось бы с дырами, которые легко не заметить
        raise NothingWritten({"ok": False, "written": 0, "skipped": skipped, "errors": errors,
                              "mode": None})
    for employee_id, days in touched.items():
        rebuild_generated_for_days(str(employee_id), days, ports)
    audit(db, principal, "schedule_range_absence", f"{payload.first}..{payload.last}",
          {"employees": payload.employee_ids, "code": code, "written": written})
    return {"ok": True, "written": written, "skipped": skipped, "errors": [], "mode": None}


class ClearMonthIn(BaseModel):
    employee_ids: Optional[list[int]] = None
    year: int
    month: int


@transactional
def reset_month(db: Session, principal: Principal, payload: ClearMonthIn) -> dict:
    """«Сбросить месяц» в Графике (решения владельца 16.10.2026): убрать РУЧНЫЕ
    смены и согласованные ОТСУТСТВИЯ месяца (отлучки-интервалы и «выходные за
    часы») и перегенерировать График из Табеля — слой 1 возвращается к чистому
    плану из слоя 0.

    Отличие от clear-month: Табель НЕ трогается (он сбрасывается из «Слой 0 ·
    Табель»). Отсутствие принадлежит месяцу по перекрытию интервала (как в сетке:
    отлучка через полночь на границе месяцев уходит в сброс своего месяца).
    Записи удаляются с аудитом; напечатанные ранее заявления остаются в истории
    журнала. Закрытые периоды не трогаются (RUL-CLOSED-PERIOD-IMMUTABLE)."""
    ensure_period(payload.year, payload.month)
    first, last = month_bounds(payload.year, payload.month)
    ports = engine_ports(db, principal, now_utc())
    emps = [db.get(Employee, i) for i in (payload.employee_ids or [])]
    emps = [e for e in emps if e is not None and e.deleted_at is None] or \
        visible_employees(db, first, last)[0]
    lo_utc, hi_utc = month_bounds_utc(first, last)
    cleared, absences_cleared, skipped = 0, 0, 0
    locks = timesheet_edit.lock_states([str(e.id) for e in emps], first, ports)
    for emp in emps:
        if locks[str(emp.id)] == "locked":
            skipped += 1
            continue
        lock_employee(db, emp.id)        # График — вход закрытия периода (TOCTOU)
        manual = list(db.scalars(select(ScheduleShift).where(
            ScheduleShift.employee_id == emp.id, ScheduleShift.source == "manual",
            ScheduleShift.date >= first, ScheduleShift.date <= last)))
        for row in manual:
            db.delete(row)
        cleared += len(manual)
        absences = list(db.scalars(select(ScheduleAbsence).where(
            ScheduleAbsence.employee_id == emp.id, ScheduleAbsence.start_utc < hi_utc,
            ScheduleAbsence.end_utc > lo_utc)))
        for row in absences:
            db.delete(row)
        absences_cleared += len(absences)
        db.flush()      # rebuild не должен видеть удалённые строки (autoflush off)
        schedule_view.rebuild_generated_schedule(str(emp.id),
                                                 month_period(payload.year, payload.month),
                                                 ports)
    audit(db, principal, "schedule_reset_month", f"{payload.year}-{payload.month:02d}",
          {"manual_shifts_cleared": cleared, "absences_cleared": absences_cleared})
    return {"ok": True, "cleared": cleared, "absences_cleared": absences_cleared,
            "skipped_employees": skipped}
