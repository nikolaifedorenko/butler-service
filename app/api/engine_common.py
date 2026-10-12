"""Общие помощники HTTP-слоя для движка v7.1: композиция портов (composition root —
`now` снимается здесь и передаётся параметром, v7.1/F-15), сотрудники периода,
тексты типизированных ошибок, лёгкие сводки для экранов отметок (БЕЗ тяжёлого
конвейера — 16.1 п.2: settle()/evaluate_flags() запускает только вкладка
«Управленческий табель»)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..employment import employed_on
from ..engine.adapters.factory import build_ports
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
