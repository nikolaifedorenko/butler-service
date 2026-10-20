"""Мост interface-слоя к движку v7.1 (application-слой модуля timesheet):
композиция портов (composition root — `now` снимается здесь и передаётся
параметром, v7.1/F-15), сотрудники периода, лёгкие сводки для экранов отметок
(БЕЗ тяжёлого конвейера — 16.1 п.2: settle()/evaluate_flags() запускает только
вкладка «Управленческий табель»). Тексты ошибок — в interface/formatting.py
(error_text, фаза C2 §5.3)."""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.employees.application import Employee, EmploymentPeriod, employed_on, group_index, normalize_group

from ..adapters.factory import build_ports
from ..adapters.orm import PeriodClosing
from ..adapters.sql_settings import base_version
from ..domain.types.entities import Period


def covers_window(st, row, day, start_local, end_local) -> bool:
    """Отсутствие покрывает рабочее окно значения Табеля дня целиком (EX-29).

    ЕДИНСТВЕННОЕ правило «выходного за часы»: его используют заявления
    (absence-period), сетка Графика (плашка и whole_shift) и Гант Факта
    (цвет дня); второй копии правила нет (дух антипаттерна 12.23)."""
    from ..domain.day_card.fmt_hours import fmt_hours

    if (end_local - start_local) >= dt.timedelta(hours=23):
        return True
    if row is None:
        return False
    policy = st.day_code_policy.get(row.code)
    if policy is None or not policy.carries_hours or not row.plan_minutes:
        return False
    window = st.windows.get(f"{row.code} {fmt_hours(row.plan_minutes)}")
    if window is None:
        return False
    midnight = dt.datetime.combine(day, dt.time(0), st.tz)
    win_start = midnight + dt.timedelta(minutes=window.start_minute)
    win_end = midnight + dt.timedelta(minutes=window.end_minute)
    return start_local <= win_start and end_local >= win_end


def color_lookups(db: Session) -> tuple[dict, dict]:
    """Словари для раскраски ячеек план/факт: (рабочие виды словаря «Смены и
    отсутствия» по окну (start,end), цвета кодов Табеля из presentation настроек).
    Один источник для Графика, Факта-Ганта и печатных форм (16.10.2026; 18.10.2026 —
    цвета отсутствий берём из кодов Табеля: связка «вид → код» удалена)."""
    from ..adapters.orm import ShiftType

    work_types: dict[tuple[str, str], ShiftType] = {}
    for x in db.scalars(select(ShiftType).order_by(ShiftType.id)):
        if x.kind == "work":
            work_types.setdefault((x.start_time, x.end_time), x)
    return work_types, day_code_colors(db)


def pick_cell_color(lookups: tuple[dict, dict], shift_hm: tuple[str, str] | None,
                    tabel_code: str | None, whole_off_color: str | None = None) -> str | None:
    """Цвет ячейки/полосы: плашка отсутствия → цвет вида; смена → цвет словарной
    смены с тем же окном; иначе — цвет кода Табеля из presentation настроек."""
    work_types, code_colors = lookups
    if whole_off_color:
        return whole_off_color
    if shift_hm:
        wt = work_types.get(shift_hm)
        if wt is not None and (wt.color or "").strip():
            return wt.color
    if tabel_code:
        return code_colors.get(tabel_code)
    return None


def day_code_colors(db: Session) -> dict[str, str]:
    """Цвета кодов Табеля — блок presentation версии справочников (данные приложения;
    домен цветов не знает, 2.4). Общий источник Табеля и Графика: пустой словарь —
    потребители берут свою подстраховку."""
    ver = base_version(db, dt.date.today())
    if ver is None:
        return {}
    try:
        payload = json.loads(ver.payload_json)
    except (ValueError, TypeError):
        return {}
    rows = payload.get("day_code_policy") or {}
    return {code: row["color"] for code, row in rows.items()
            if isinstance(row, dict) and row.get("color")}


def now_utc() -> dt.datetime:
    """Системное время в composition root (7.1, v7.1/F-15): передаётся в use case'ы."""
    return dt.datetime.now(dt.timezone.utc)


def engine_ports(db: Session, principal=None, now: dt.datetime | None = None):
    """Порты движка для одного запроса; actor — имя пользователя для аудита закрытий."""
    return build_ports(db, now or now_utc(),
                       getattr(principal, "name", "") if principal else "")


def period_employees(db: Session, first: dt.date, last: dt.date,
                     ids: list[int] | None = None) -> list[Employee]:
    """Сотрудники, трудоустроенные хотя бы один день периода (R35: периоды вне
    трудоустройства не показываются)."""
    q = select(Employee).where(Employee.deleted_at.is_(None))
    if ids:
        q = q.where(Employee.id.in_(ids))
    emps = list(db.scalars(q))
    periods: dict[int, list] = {}
    for p in db.scalars(select(EmploymentPeriod).where(EmploymentPeriod.employee_id.in_(
            [e.id for e in emps]))):
        periods.setdefault(p.employee_id, []).append(p)

    def visible(e: Employee) -> bool:
        recs = periods.get(e.id)
        if not recs:
            return e.active
        return any(employed_on(recs, first + dt.timedelta(days=i))
                   for i in range((last - first).days + 1))

    out = [e for e in emps if visible(e)]
    out.sort(key=lambda e: (group_index(normalize_group(e.schedule_group)), e.full_name))
    return out


def emp_brief(e: Employee) -> dict:
    return {"id": e.id, "full_name": e.full_name, "short_name": e.display_name,
            "position": e.position or "", "group": normalize_group(e.schedule_group) or "Другие смены",
            "color": e.group_color, "tab_number": e.tab_number or ""}


def last_closed_bank(db: Session, emp_id: int) -> tuple[float | None, Period | None]:
    """Банк последнего закрытого периода — чтение из хранилища БЕЗ домена
    (RUL-CLOSED-PERIOD-IMMUTABLE): «сейчас» банк показывается только закрытым итогом."""
    row = db.scalar(select(PeriodClosing).where(PeriodClosing.employee_id == emp_id)
                    .order_by(PeriodClosing.period_end.desc()).limit(1))
    if row is None:
        return None, None
    return round(row.closing_bank_minutes / 60, 2), Period(row.period_start, row.period_end)


def day_code_rows(db: Session, day: dt.date | None = None) -> dict[str, dict]:
    """Строки CFG-DAY-CODES действующей версии справочников — данные приложения.

    Домен читает их как `Settings.day_code_policy`, но HTTP-слою список нужен там,
    где домен не участвует: редактор словаря смен проверяет, что «код в табеле»
    существует (T1, норматив 12.10.2026), health-панель сверяет два справочника
    (APP-SHIFT-CODE / APP-CODE-NO-SHIFT). Порядок — как в payload версии: тот же,
    что видит экран «Коды Табеля».

    Пустой словарь означает «действующей версии ещё нет» (свежая база до bootstrap),
    а не «кодов нет»: вызывающий код в этом случае проверку пропускает.
    """
    import json

    from app.core.time import local_date

    from ..adapters.sql_settings import base_version

    ver = base_version(db, day or local_date())
    if ver is None:
        return {}
    try:
        raw = json.loads(ver.payload_json).get("day_code_policy") or {}
    except (TypeError, ValueError, AttributeError):
        return {}
    out: dict[str, dict] = {}
    for code, row in raw.items():
        if not isinstance(row, dict):
            continue
        out[str(code)] = {"code": str(code), "title": str(row.get("title") or ""),
                          "carries_hours": bool(row.get("carries_hours")),
                          "accepts_ut": bool(row.get("accepts_ut")),
                          "counts_in_ut": bool(row.get("counts_in_ut")),
                          # режим отметок и шаблон заявления — атрибуты карточки кода
                          # (решение владельца 16.10.2026). Отсутствующий ключ в старой
                          # версии = разрешение (RUL-ALL-MARKS-COUNTED), заявления нет.
                          "punch_in": bool(row.get("punch_in", True)),
                          "punch_out": bool(row.get("punch_out", True)),
                          "doc_type": str(row.get("doc_type") or "")}
    return out
