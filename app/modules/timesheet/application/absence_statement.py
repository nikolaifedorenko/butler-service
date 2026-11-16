"""Заявления по отсутствиям Графика: какой документ печатать, за какой период и на сколько часов.

Единая сущность «отпросился (выходной за часы)» (решение владельца 12.10.2026): один вид
словаря, две точки ввода — интервал части смены либо вся смена. Заявление выбирается по
точке ввода: на всю смену — «выходной за ранее отработанные часы», интервал — «об
отсутствии на рабочем месте»."""
from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.core.format import hours_text
from app.core.time import TZ
from app.modules.people.application import Employee, suggest_genitive

from ..adapters.orm import ScheduleAbsence, ShiftType, TabelDay
from .engine_common import covers_window, day_code_colors, day_code_rows
from .months import month_period
from .schedule_grid import period_settings
from .schedule_helpers import DEFAULT_RULES, load_rules
from .statement_kinds import statement_kind_exists
from .texts import fmt_hours_strict

DOC_WHOLE_SHIFT = "day_off_hours"
DOC_PARTIAL_SHIFT = "time_off_request"


def doc_type_of_absence(db: Session, kind: ShiftType, whole_shift: bool) -> str:
    """Какое заявление печатать по отсутствию.

    Словарь смен с 18.10.2026 содержит единственный вид отсутствия — системный
    «Отпросился (выходной за часы)»: документ зависит от точки ввода (вся смена —
    «выходной за ранее отработанные часы», интервал — «об отсутствии на рабочем
    месте»). Если нужный вид заявления удалён владельцем, остаётся привязка самого
    вида смены.
    """
    own = (kind.doc_type or "").strip()
    wanted = DOC_WHOLE_SHIFT if whole_shift else DOC_PARTIAL_SHIFT
    return wanted if statement_kind_exists(db, wanted) else own


def standard_day_hours(db: Session, st, emp, day: dt.date) -> tuple[Optional[float], str]:
    """Часы «выходного за ранее отработанные часы» — стандартное окно смен сотрудника.

    Порядок вывода (норматив от 12.10.2026):

    1. `window_of_day` — окно значения Табеля этого дня (или дня, который сотрудник
       меняет на выходной): сколько часов он обычно работает, столько и стоит в
       заявлении;
    2. `timesheet_mode` — мода длин окон в Табеле сотрудника за последние 90 дней:
       день ещё не заполнен, но норма сотрудника понятна;
    3. `default` — глобальная настройка объекта (`timeoff_default_hours`).

    Число информационное: код отсутствия не несёт плановых часов, согласованное
    отсутствие не влияет на план, часы и банк (RUL-ABSENCE-ONLY-FLAGS), недостачу дня
    гасит банк (EX-29).
    """
    def window_hours(row) -> Optional[float]:
        if row is None:
            return None
        policy = st.day_code_policy.get(row.code)
        if policy is None or not policy.carries_hours or not row.plan_minutes:
            return None
        window = st.windows.get(f"{row.code} {fmt_hours_strict(row.plan_minutes, row.employee_id, row.date)}")
        return None if window is None else window.length / 60

    own = window_hours(db.scalar(select(TabelDay).where(TabelDay.employee_id == emp.id,
                                                        TabelDay.date == day)))
    if own is not None:
        return own, "window_of_day"
    # день, который меняют на выходной: ближайший предыдущий рабочий день сотрудника
    for back in range(1, 15):
        prev = window_hours(db.scalar(select(TabelDay).where(
            TabelDay.employee_id == emp.id, TabelDay.date == day - dt.timedelta(days=back))))
        if prev is not None:
            return prev, "window_of_day"
    since = day - dt.timedelta(days=90)
    lengths = [window_hours(r) for r in db.scalars(select(TabelDay).where(
        TabelDay.employee_id == emp.id, TabelDay.date >= since, TabelDay.date <= day))]
    known = [v for v in lengths if v is not None]
    if known:
        return Counter(known).most_common(1)[0][0], "timesheet_mode"
    rules = load_rules(db)
    try:
        return float(rules.get("timeoff_default_hours", DEFAULT_RULES["timeoff_default_hours"])), "default"
    except (TypeError, ValueError):
        return float(DEFAULT_RULES["timeoff_default_hours"]), "default"


def st_day(db: Session, day: dt.date):
    """Настройки периода, содержащего день (для вывода часов отсутствия)."""
    return period_settings(db, month_period(day.year, day.month))


def _covers_whole_day(db: Session, st, employee_id: int, day: dt.date,
                      start_local: dt.datetime, end_local: dt.datetime) -> bool:
    """Отсутствие покрывает рабочую часть дня целиком.

    Признак «дня за часы»: сравниваем с окном значения Табеля этого дня (12 часовая
    смена 08:00–20:00 покрыта записью 08:00–20:00), а не с календарными сутками —
    иначе заявление печаталось бы с длиной записи вместо нормы смены.
    """
    row = db.scalar(select(TabelDay).where(TabelDay.employee_id == employee_id,
                                           TabelDay.date == day))
    return covers_window(st, row, day, start_local, end_local)


def timeoff_hours(db: Session, employee_id: int, date: dt.date) -> dict:
    """Часы «выходного за ранее отработанные часы» для сотрудника и дня.

    Значение выводится, а не задаётся константой (норматив от 12.10.2026):
    стандартное окно смен сотрудника из Табеля → мода окон за 90 дней → глобальный
    fallback. `hours_source` показывает, какое правило сработало.
    """
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise NotFound("Сотрудник не найден")
    st = period_settings(db, month_period(date.year, date.month))
    value, source = standard_day_hours(db, st, emp, date)
    return {"employee_id": employee_id, "date": date.isoformat(), "hours": value,
            "hours_source": source}


def _interval_info(db: Session, emp: Optional[Employee], row: ScheduleAbsence) -> Optional[dict]:
    """Интервал согласованного отсутствия как фрагмент заявления.

    None — запись без вида словаря либо у вида нет заявления (doc_type пуст):
    в печатный период такой интервал не входит. Часы: «вся смена» — стандартное
    окно смен сотрудника (норматив 12.10.2026, EX-29), интервал — длина записи."""
    if not row.kind_id:
        return None
    kind = db.get(ShiftType, row.kind_id)
    if kind is None:
        return None
    start_local = row.start_utc.astimezone(TZ)
    end_local = row.end_utc.astimezone(TZ)
    day = start_local.date()
    day_settings = st_day(db, day)
    whole_shift = _covers_whole_day(db, day_settings, row.employee_id, day,
                                    start_local, end_local)
    # шаблон заявления: выбранный в диалоге (18.10.2026) первее правила по точке входа
    doc = (row.doc_type or "").strip() or doc_type_of_absence(db, kind, whole_shift)
    if not doc:
        return None
    if whole_shift:
        hours_value, hours_source = standard_day_hours(db, day_settings, emp, day)
    else:
        hours_value = round((end_local - start_local).total_seconds() / 3600, 2)
        hours_source = "absence_interval"
    return {"id": row.id,
            "start": day.isoformat(),
            "end": (end_local - dt.timedelta(seconds=1)).date().isoformat(),
            "from_time": start_local.strftime("%H:%M"),
            "until_time": end_local.strftime("%H:%M"),
            "hours": hours_value, "hours_source": hours_source,
            "whole_shift": whole_shift, "kind": _kind_brief(kind),
            "note": row.note or "",
            "doc_type": doc}


def absence_period(db: Session, employee_id: int, date: dt.date,
                   absence_id: Optional[int] = None) -> dict:
    """Непрерывный период одного отсутствия вокруг даты — для печати заявления.

    Источник — Табель (коды отсутствий) либо записи согласованного отсутствия
    («отпросился»): заявление находит весь период, даже если он пересекает границы
    месяцев.

    Отлучек в одном дне может быть несколько (решение владельца 16.10.2026):
    по умолчанию заявление ОДНО на все интервалы дня (`intervals`, `intervals_text`
    — перечень «с 14:00 до 16:00 (2 ч) и с 18:00 до 20:00 (2 ч)», `hours` — сумма);
    с `absence_id` — заявление по одному выбранному интервалу."""
    emp = db.get(Employee, employee_id)
    employee_payload = None if emp is None else {
        "id": emp.id, "full_name": emp.full_name, "short_name": emp.display_name,
        "full_name_genitive": emp.full_name_genitive or suggest_genitive(emp.full_name),
        "position": emp.position, "tab_number": emp.tab_number or "",
        "nationality": emp.nationality or "", "subdivision": emp.subdivision or "",
        "department": emp.department.name if emp.department else "",
    }
    # 1) согласованные отсутствия дня («отпросился») — записи Графика с типом-заявлением
    day_lo = dt.datetime.combine(date, dt.time(0), TZ).astimezone(dt.UTC)
    day_hi = day_lo + dt.timedelta(days=1)
    day_rows = list(db.scalars(select(ScheduleAbsence).where(
        ScheduleAbsence.employee_id == employee_id, ScheduleAbsence.start_utc < day_hi,
        ScheduleAbsence.end_utc > day_lo).order_by(ScheduleAbsence.start_utc)))
    intervals = [iv for iv in (_interval_info(db, emp, r) for r in day_rows) if iv]
    if absence_id is not None:
        intervals = [iv for iv in intervals if iv["id"] == absence_id]
        if not intervals:
            raise NotFound("Интервал отсутствия не найден в этот день")
    if intervals:
        first, last = intervals[0], intervals[-1]
        total = round(sum(iv["hours"] or 0 for iv in intervals), 2)
        one = len(intervals) == 1
        doc_types = {iv["doc_type"] for iv in intervals}
        if len(doc_types) == 1:
            doc_type = doc_types.pop()
        else:
            # смешанные точки ввода (вся смена + интервал): перечень интервалов
            # печатается заявлением «об отсутствии на рабочем месте»
            doc_type = (DOC_PARTIAL_SHIFT if statement_kind_exists(db, DOC_PARTIAL_SHIFT)
                        else first["doc_type"])
        intervals_text = " и ".join(
            f"с {iv['from_time']} до {iv['until_time']} ({hours_text(iv['hours'] or 0)} ч)"
            for iv in intervals)
        return {"employee": employee_payload,
                "source": "schedule_absence",
                "whole_shift": all(iv["whole_shift"] for iv in intervals),
                "doc_type": doc_type,
                "start": first["start"], "end": last["end"], "days": 1,
                "shift": first["kind"], "note": first["note"],
                "hours": total,
                "hours_source": first["hours_source"] if one else "combined",
                "partial": {"from_time": first["from_time"],
                            "until_time": last["until_time"],
                            "hours": total,
                            "hours_source": first["hours_source"] if one else "combined",
                            "kind": first["kind"]},
                "intervals": intervals, "intervals_text": intervals_text,
                "notes": sorted({iv["note"] for iv in intervals if iv["note"]})}
    # 2) отсутствие на период — непрерывный диапазон одного кода Табеля
    rows = {r.date: r for r in db.scalars(select(TabelDay).where(
        TabelDay.employee_id == employee_id).order_by(TabelDay.date))}
    anchor = rows.get(date)
    if anchor is None:
        raise NotFound("В эту дату нет назначенного отсутствия")
    start = end = date
    d = date - dt.timedelta(days=1)
    while d in rows and rows[d].code == anchor.code:
        start = d
        d -= dt.timedelta(days=1)
    d = date + dt.timedelta(days=1)
    while d in rows and rows[d].code == anchor.code:
        end = d
        d += dt.timedelta(days=1)
    # Шаблон заявления — атрибут КАРТОЧКИ кода Табеля (решение владельца
    # 16.10.2026): doc_type строки day_code_policy первее привязки словарного вида
    # (вид может отсутствовать — словарь смен только про График).
    code_row = day_code_rows(db, date).get(anchor.code) or {}
    code_doc = (code_row.get("doc_type") or "").strip()
    doc_type = code_doc if code_doc and statement_kind_exists(db, code_doc) else ""
    if not doc_type:
        raise NotFound(f"Для кода «{anchor.code}» не настроен тип заявления")
    st = period_settings(db, month_period(start.year, start.month))
    hours_value, hours_source = standard_day_hours(db, st, emp, start)
    return {"employee": employee_payload,
            "source": "tabel_code", "whole_shift": True,
            "doc_type": doc_type,
            "start": start.isoformat(), "end": end.isoformat(),
            "days": (end - start).days + 1,
            "shift": {"id": None, "code": anchor.code, "kind": "absence",
                      "name": code_row.get("title") or anchor.code,
                      "color": day_code_colors(db).get(anchor.code, ""),
                      "doc_type": doc_type},
            "note": anchor.note or "", "partial": None,
            "intervals": None, "intervals_text": None,
            "hours": hours_value, "hours_source": hours_source,
            "notes": sorted({r.note for d_, r in rows.items() if start <= d_ <= end and r.note})}


def _kind_brief(kind: ShiftType) -> dict:
    return {"id": kind.id, "code": kind.code, "name": kind.name, "kind": kind.kind,
            "color": kind.color, "doc_type": kind.doc_type or ""}
