"""Мост API-слоя к движку v7.1 (сервисный слой): композиция портов (composition root —
`now` снимается здесь и передаётся параметром, v7.1/F-15), сотрудники периода,
тексты типизированных ошибок, лёгкие сводки для экранов отметок (БЕЗ тяжёлого
конвейера — 16.1 п.2: settle()/evaluate_flags() запускает только вкладка
«Управленческий табель»)."""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..employment import employed_on
from ..engine.adapters.factory import build_ports
from ..engine.adapters.sql_settings import base_version
from ..engine.application.errors import ApplicationError
from ..engine.domain.types.entities import Period
from ..engine.domain.types.errors import (
    ConfigError,
    IncompletePeriodError,
    IncompleteTimesheetError,
    InvalidInputDataError,
    InvariantViolationError,
    UnknownDayCodeError,
    UnknownTimesheetValueError,
)
from ..groups import group_index, normalize_group
from ..models import Employee, EmploymentPeriod, PeriodClosing


def covers_window(st, row, day, start_local, end_local) -> bool:
    """Отсутствие покрывает рабочее окно значения Табеля дня целиком (EX-29).

    ЕДИНСТВЕННОЕ правило «выходного за часы»: его используют заявления
    (absence-period), сетка Графика (плашка и whole_shift) и Гант Факта
    (цвет дня); второй копии правила нет (дух антипаттерна 12.23)."""
    from ..engine.domain.day_card.fmt_hours import fmt_hours

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


def color_lookups(db: Session) -> tuple[dict, dict, dict]:
    """Словари для раскраски ячеек план/факт из словаря «Смены и отсутствия»:
    (рабочие виды по окну (start,end), виды отсутствий по tzh_code, цвета кодов
    Табеля). Один источник для Графика, Факта-Ганта и печатных форм (16.10.2026)."""
    from ..models import ShiftType

    work_types: dict[tuple[str, str], ShiftType] = {}
    absence_types: dict[str, ShiftType] = {}
    for x in db.scalars(select(ShiftType).order_by(ShiftType.id)):
        if x.kind == "work":
            work_types.setdefault((x.start_time, x.end_time), x)
        elif x.kind == "absence" and (x.tzh_code or "").strip():
            absence_types.setdefault(x.tzh_code.strip(), x)
    return work_types, absence_types, day_code_colors(db)


def pick_cell_color(lookups: tuple[dict, dict, dict], shift_hm: tuple[str, str] | None,
                    tabel_code: str | None, whole_off_color: str | None = None) -> str | None:
    """Цвет ячейки/полосы: плашка отсутствия → цвет вида; смена → цвет словарной
    смены с тем же окном; код без смены → цвет вида по tzh_code; запасной — цвет
    кода Табеля из presentation настроек."""
    work_types, absence_types, code_colors = lookups
    if whole_off_color:
        return whole_off_color
    if shift_hm:
        wt = work_types.get(shift_hm)
        if wt is not None and (wt.color or "").strip():
            return wt.color
    elif tabel_code:
        at = absence_types.get(tabel_code)
        if at is not None and (at.color or "").strip():
            return at.color
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


ERROR_TEXTS = {
    "PERIOD_OUTSIDE_EMPLOYMENT": "Период вне интервала трудоустройства — не рассчитывается",
    "PREVIOUS_PERIOD_NOT_CLOSED": "Сначала закройте предыдущий период (либо задайте начальный "
                                  "банк первого периода корректировкой OPENING_SEED)",
    "PERIOD_ALREADY_CLOSED": "Период уже закрыт",
    "PERIOD_NOT_CLOSED": "Период не закрыт — пересчитывать нечего",
    "RECALCULATION_FORBIDDEN": "Пересчитать можно только последний закрытый период "
                               "(следующий уже закрыт)",
    "SCHEDULE_DAY_NOT_EDITABLE": "День не редактируем: ручную смену можно поставить только "
                                 "в день, принимающий коды УТ (accepts_ut = Да)",
    "TIMESHEET_LOCKED": "Период закрыт, и следующий уже закрыт — править можно только "
                        "последний закрытый период",
    "TIMESHEET_OUTSIDE_EMPLOYMENT": "День вне периода трудоустройства сотрудника — "
                                    "Табель за такие дни не ведётся",
    "SEED_NOT_ALLOWED": "Начальный банк (OPENING_SEED) задаётся только для первого периода "
                        "сотрудника",
    "ADJUSTMENT_CLOSED_PERIOD": "Период закрыт — корректировка возможна только через пересчёт",
    "CHK-PUNCH-SEQUENCE": "Недопустимая последовательность отметок («пришёл»/«ушёл» не "
                          "чередуются). Исправьте отметки: расчёт не «чинит» последовательность",
    "CHK-DAYS-IN-PERIOD": "В Табеле есть строки вне эффективного периода (вне трудоустройства)",
    "CHK-PERIOD-BOUNDS": "Период задан неверно: начало позже конца",
    "CHK-NOW-IN-PERIOD": "Период ещё не начался",
    "CHK-DEFERRED-IN": "Некорректные входящие переносы",
    "CHK-OPENING": "Некорректные входящие остатки/корректировки",
    "CHK-PLAN-CONSISTENT": "План не согласован с кодом: код с часами требует план > 0, "
                           "код без часов — план 0",
    "CHK-PLAN-FORMAT": "Плановые часы должны быть кратны 15 минутам",
    "CHK-SINGLE-EMPLOYEE": "Строки Табеля относятся к разным сотрудникам",
    "CHK-GROUP-EXISTS": "Группа сотрудника отсутствует в реестре CFG-GROUPS",
}


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


def domain_error_text(exc: Exception) -> str:
    if isinstance(exc, ConfigError):
        # человеческие тексты нарушений — в interface (2.4): домен возвращает код и контекст
        from ..engine.interface.formatting import config_violation_text
        texts = [f"{config_violation_text(c, dict(d))} [{c}]" for c, d in exc.violations]
        return "Ошибка настроек: " + "; ".join(texts)
    if isinstance(exc, UnknownDayCodeError):
        return f"Код Табеля «{exc.code}» ({exc.day:%d.%m}) отсутствует в справочнике CFG-DAY-CODES"
    if isinstance(exc, UnknownTimesheetValueError):
        return (f"Для значения Табеля «{exc.value}» нет строки CFG-WINDOWS — "
                "добавьте окно в настройках движка (паттерн EX-15)")
    if isinstance(exc, IncompleteTimesheetError):
        missing = ", ".join(f"{d:%d.%m}" for d in exc.missing[:6])
        dup = ", ".join(f"{d:%d.%m}" for d in exc.duplicated[:6])
        return ("Табель не покрывает период" + (f": пропущены {missing}" if missing else "")
                + (f"; дублируются {dup}" if dup else ""))
    if isinstance(exc, IncompletePeriodError):
        return f"Период ещё не завершён: закрыть можно с 00:00 {exc.period_end + dt.timedelta(days=1):%d.%m.%Y}"
    if isinstance(exc, InvalidInputDataError):
        base = ERROR_TEXTS.get(exc.code, f"Ошибка входных данных ({exc.code})")
        return base if exc.code in ERROR_TEXTS else f"{base}: {exc.data}"
    if isinstance(exc, InvariantViolationError):
        return f"Внутренняя ошибка расчёта (инвариант {exc.code}) — результат не сохранён"
    if isinstance(exc, ApplicationError):
        return ERROR_TEXTS.get(exc.code, str(exc))
    return str(exc)


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

    from ..deps import local_date
    from ..engine.adapters.sql_settings import base_version

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
