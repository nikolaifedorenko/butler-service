"""Человекочитаемые тексты флагов, исключений и трассы — только здесь (0.1 п.7, 2.4,
12.13). Тексты собираются по коду и параметрам Reason/Flag (реестры 6.2, 6.6)."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from ..domain.codes_registry import flag_codes as F
from ..domain.codes_registry import reason_codes as R

FLAG_TITLES = {
    F.LATE: "Опоздание",
    F.EARLY_DEPARTURE: "Ранний уход",
    F.OFF_SHIFT_ATTENDANCE: "Работа вне Графика",
}
FLAG_SEVERITY = {F.LATE: "warn", F.EARLY_DEPARTURE: "warn", F.OFF_SHIFT_ATTENDANCE: "info"}
REASON_TITLES = {
    R.OPENING_ROUNDED: "Входящий остаток нормализован к новому шагу",
    R.PLAN_EQUALS_FACT: "Применён «План=Факт»",
    R.UNPAID_CREDITED: "Неоплачиваемая переработка зачислена в банк",
    R.CODE_PLACED: "Код перенесён в день",
    R.NO_RECEIVER: "Нет дня-приёмника — код отложен на следующий период",
    R.BANK_APPLIED: "Недостача погашена банком",
    R.CODE_CUT: "Код изъят в погашение недостачи",
    R.RESIDUAL_CARRIED: "Остаток недостачи перенесён минусом банка",
}


def hm(minutes: int) -> str:
    return "24:00" if minutes >= 1440 else f"{minutes // 60:02d}:{minutes % 60:02d}"


def local_hm(value, tz) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value)
    return value.astimezone(ZoneInfo(str(tz))).strftime("%H:%M")


def hours(minutes: int) -> str:
    return f"{minutes / 60:g}"


def hours_text(minutes: int) -> str:
    """Часы для записи Табеля: 720 → «12», 645 → «10,75» (та же нотация, что value_of)."""
    from ..domain.day_card.fmt_hours import fmt_hours
    return fmt_hours(minutes)


def fmt_hours_strict(minutes: int, employee_id, day) -> str:
    """Часы строки Табеля для ОТКРЫТИЯ вкладок (P1-ts-3, строгий вариант).

    Доменный fmt_hours канонически строг (§3.3): план обязан быть кратен 15
    (CHK-PLAN-FORMAT), иначе значение непредставимо. Конвейер отбраковывает такие
    строки на стадии 1, а дисплейные пути читают Табель напрямую — легаси/битая
    строка роняла вкладку сырым ValueError (500). Здесь отказ типизирован:
    TimesheetRowCorruptError (409) с указанием сотрудника, дня и значения —
    вкладка честно сообщает о повреждении данных.
    """
    from ..application.errors import TimesheetRowCorruptError
    from ..domain.day_card.fmt_hours import fmt_hours
    try:
        return fmt_hours(minutes)
    except ValueError as exc:
        raise TimesheetRowCorruptError(employee_id, day, minutes) from exc


def code_with_hours(tariff: str, minutes: int) -> str:
    """Нотация отображения кода УТ (CFG-WEIGHTS): «ДЯ2 3» — ровно один пробел."""
    return f"{tariff} {hours(minutes)}"


def _segments_text(segments, tz) -> str:
    if not segments:
        return "—"
    return ", ".join(f"{local_hm(s, tz)}–{local_hm(e, tz)}" for s, e in segments)


def flag_text(code: str, data: dict, tz) -> str:
    """Текст флага по коду и параметрам (6.6: семантика ключей data)."""
    if code == F.LATE:
        actual = data.get("actual_at")
        expected = local_hm(data.get("expected_at"), tz)
        if actual is None:
            return f"Ожидался в {expected} — не пришёл"
        return f"Опоздание: ожидался в {expected}, пришёл в {local_hm(actual, tz)}"
    if code == F.EARLY_DEPARTURE:
        return (f"Ранний уход: в {local_hm(data.get('actual_at'), tz)} "
                f"вместо {local_hm(data.get('expected_at'), tz)}")
    if code == F.OFF_SHIFT_ATTENDANCE:
        return (f"Присутствие с {local_hm(data.get('first_presence_at'), tz)} "
                f"в день «{data.get('day_code')}», когда по Графику не ожидался")
    return code


def flag_hint(code: str, data: dict, tz) -> str:
    """Пояснение к флагу для карточки дня (не нормативно — удобство UI)."""
    if code == F.OFF_SHIFT_ATTENDANCE:
        return (f"Смена: {_segments_text(data.get('shift_segments'), tz)}; "
                f"отсутствия: {_segments_text(data.get('absence_intervals'), tz)}")
    return ""


def reason_text(code: str, data: dict) -> str:
    title = REASON_TITLES.get(code, code)
    if code == R.CODE_PLACED:
        return (f"{title}: {code_with_hours(data['tariff'], data['minutes'])} "
                f"из {data['source_day']} в {data['placed_day']}")
    if code == R.CODE_CUT:
        return (f"{title}: {code_with_hours(data['tariff'], data['taken_minutes'])} "
                f"({data['source_day']}), погашено {hours(data['paid_minutes'])} ч")
    if code == R.UNPAID_CREDITED:
        return (f"{title}: {data['day']} {code_with_hours(data['tariff'], data['taken_minutes'])} → "
                f"{hours(data['credited_minutes'])} ч банка")
    if code == R.BANK_APPLIED:
        return f"{title}: {hours(data['used'])} ч"
    if code == R.NO_RECEIVER:
        return f"{title}: {code_with_hours(data['tariff'], data['minutes'])} ({data['source_day']})"
    if code == R.RESIDUAL_CARRIED:
        return f"{title}: {hours(data['residual_minutes'])} ч"
    if code == R.OPENING_ROUNDED:
        return (f"{title}: {data['before_minutes']} → {data['after_minutes']} мин "
                f"(шаг {data['old_step_minutes']} → {data['new_step_minutes']})")
    if code == R.PLAN_EQUALS_FACT:
        return (f"{title}: план {hours(data['plan_before'])} → {hours(data['plan_after'])} ч "
                f"(источник: {data['policy']})")
    return title


# ───────────────────── нарушения конфигурации (CHK-*) ─────────────────────
# Тексты проверок уровня 1 (5.3): домен возвращает (код, минимальный контекст),
# а человекочитаемое сообщение собирается только здесь (2.4, 12.13).
CONFIG_TITLES = {
    "CFG-TZ": "Некорректный часовой пояс (tz) в сохранённых настройках",
    "CHK-WINDOW-PLAN": "Информационный план значения больше длины окна",
    "CHK-WINDOW-BOUNDS": "Некорректные границы окна",
    "CHK-WINDOW-KEY": "Некорректный ключ строки окон",
    "CHK-CATEGORIES-COVER": "Категории времени не покрывают сутки",
    "CHK-CODES-EXIST": "Нет кода УТ для категории и веса",
    "CHK-CASCADE-FULL": "Порядок каскада неполный",
    "CHK-PLACEMENT-FULL": "Порядок размещения неполный",
    "CHK-WEIGHTS-POSITIVE": "Некорректный вес кода УТ",
    "CHK-STEP-DIVIDES-60": "Шаг расчёта не делит час без остатка",
    "CHK-GRID": "Граница не кратна шагу расчёта",
    "CHK-DEFAULTS": "Не задан глобальный дефолт модификатора",
    "CHK-MODIFIER-SCOPE": "Недопустимая область действия правила",
    "CHK-MODIFIER-TYPE": "Тип значения не соответствует правилу",
    "CHK-MODIFIER-CONFLICT": "Два правила одного уровня на один день",
}
MODIFIER_TITLES = {
    "double_overtime": "Двойные переработки",
    "pays_overtime": "Оплачиваются ли переработки",
    "plan_equals_fact": "План=Факт",
    "counts_in_ut": "Учитываются ли часы в УТ",
    "late_limit_minutes": "Лимит опоздания",
}
SCOPE_FORMS = {
    1: "сотрудник + день", 2: "сотрудник + период", 3: "группа + день",
    4: "группа + период", 5: "все сотрудники + день", 6: "все сотрудники + период",
    7: "глобальный дефолт",
}
WINDOW_KEY_REASONS = {
    "non_canonical_format": "ключ неканоничен: нужен формат «код часы» через один пробел, "
                            "дробь через запятую, не более двух знаков, без хвостовых нулей",
    "unknown_day_code": "кода нет в справочнике кодов Табеля",
    "code_carries_no_hours": "код не несёт плановых часов — окна у него быть не может",
}


def _date(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        try:
            value = dt.date.fromisoformat(value)
        except ValueError:
            return value
    return f"{value:%d.%m.%Y}"


def _scope_text(scope: dict) -> str:
    """Область действия правила словами: «группа «Смена 1», 12.10.2026»."""
    if not scope:
        return "—"
    who = (f"сотрудник #{scope['employee_id']}" if scope.get("employee_id")
           else f"группа «{scope['group']}»" if scope.get("group") else "все сотрудники")
    when = (_date(scope["day"]) if scope.get("day") else
            f"{_date(scope.get('period_start'))} — {_date(scope.get('period_end'))}"
            if scope.get("period_start") else "без привязки ко времени")
    return f"{who}, {when}"


def config_violation_text(code: str, data: dict | None = None) -> str:
    """Одно нарушение конфигурации — одной фразой, с указание на что править."""
    data = data or {}
    title = CONFIG_TITLES.get(code, code)
    if code == "CFG-TZ":
        return (f"{title}: «{data.get('tz')}» — укажите существующий часовой пояс "
                "(например, Europe/Moscow) в редакторе настроек движка")
    if code == "CHK-MODIFIER-CONFLICT":
        scopes = data.get("scopes") or ({}, {})
        level = data.get("level")
        names = MODIFIER_TITLES.get(data.get("name"), data.get("name", "правило"))
        where = f" на {_date(data['day'])}" if data.get("day") else ""
        return (f"{title}: «{names}»{where} — форма области «{SCOPE_FORMS.get(level, level)}». "
                f"Записи: {_scope_text(scopes[0])} и {_scope_text(scopes[-1])}. "
                "Оставьте одну из них либо сузьте область (например, до одного сотрудника)")
    if code == "CHK-WINDOW-KEY":
        return (f"{title}: значение «{data.get('value')}» — "
                f"{WINDOW_KEY_REASONS.get(data.get('reason'), data.get('reason', ''))}")
    if code == "CHK-WINDOW-PLAN":
        return (f"{title}: «{data.get('value')}» — план {hours(data.get('plan_minutes', 0))} ч "
                f"при окне {hours(data.get('window_length', 0))} ч. План строки Табеля не превышает "
                "длину окна (зарплатная норма), а план карточки всегда равен окну")
    if code == "CHK-WINDOW-BOUNDS":
        return (f"{title}: «{data.get('value')}» — {hm(data.get('start_minute', 0))}–"
                f"{hm(data.get('end_minute', 0))}. Начало должно быть раньше конца, окно не "
                "пересекает полночь: смена через полночь оформляется одним значением в дне начала")
    if code == "CHK-GRID":
        kind = {"window": "граница окна", "category": "граница категории"}.get(
            data.get("kind"), "граница")
        return (f"{title}: {kind} «{data.get('value')}» — {hm(data.get('minute', 0))} "
                "не кратна шагу расчёта")
    if code == "CHK-CATEGORIES-COVER":
        holes = ", ".join(hm(m) for m in (data.get("holes") or ())[:4])
        overlaps = ", ".join(hm(m) for m in (data.get("overlaps") or ())[:4])
        return (f"{title}: сутки должны быть покрыты без дыр и пересечений"
                + (f"; не покрыто: {holes}" if holes else "")
                + (f"; пересечение: {overlaps}" if overlaps else ""))
    if code == "CHK-CODES-EXIST":
        return (f"{title}: для категории «{data.get('category')}» и веса {data.get('weight')} "
                f"нужен код «{data.get('expected_code')}» в таблице весов")
    if code in ("CHK-CASCADE-FULL", "CHK-PLACEMENT-FULL"):
        what = "каскада" if code == "CHK-CASCADE-FULL" else "размещения"
        parts = []
        if data.get("missing"):
            parts.append("не хватает: " + ", ".join(map(str, data["missing"])))
        if data.get("duplicates"):
            parts.append("повторяются: " + ", ".join(map(str, data["duplicates"])))
        if data.get("unknown"):
            parts.append("нет в таблице весов: " + ", ".join(map(str, data["unknown"])))
        return (f"{title}: порядок {what} обязан содержать все коды весов без повторов"
                + (" — " + "; ".join(parts) if parts else ""))
    if code == "CHK-WEIGHTS-POSITIVE":
        return (f"{title}: «{data.get('code')}» = {data.get('weight')} — нужно целое "
                "число больше нуля")
    if code == "CHK-STEP-DIVIDES-60":
        return (f"{title}: шаг {data.get('step_minutes')} мин — допустимы 1, 2, 3, 4, 5, 6, "
                "10, 12, 15, 20, 30, 60")
    if code == "CHK-DEFAULTS":
        name = MODIFIER_TITLES.get(data.get("modifier"), data.get("modifier"))
        extra = (f" (получено {data['value']!r})" if "value" in data else
                 " — задайте глобальное значение: без него расчёт остановится")
        return f"{title}: «{name}»{extra}"
    if code == "CHK-MODIFIER-SCOPE":
        reason = {"invalid_scope_form": "область действия не входит в шесть допустимых форм "
                                       "(сотрудник/группа/все × день/период)",
                  "unknown_group": "группы нет в справочнике групп"}.get(
                      data.get("reason"), data.get("reason", ""))
        entry = data.get("entry") or {}
        return f"{title}: {reason}" + (f" — {_scope_text(entry)}" if entry else "")
    if code == "CHK-MODIFIER-TYPE":
        name = MODIFIER_TITLES.get(data.get("name"), data.get("name"))
        allowed = ("«да»/«нет»/«авто»" if data.get("name") == "plan_equals_fact" else "«да»/«нет»")
        return f"{title}: «{name}» = {data.get('value')!r}, допустимые значения {allowed}"
    return title


# ── Тексты типизированных ошибок движка (фаза C2, EXECUTION-SPEC-v2 §5.3) ──
# Единственное место сборки человеческих текстов доменных/прикладных ошибок.
# Центральные HTTP-хэндлеры (main.py) и payload-ошибки вкладок (200 + "error")
# используют одну и ту же функцию — раньше она звалась domain_error_text и
# жила в сервисном слое (application), что смешивало слои (2.4: тексты — только
# в interface).
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


def error_text(exc: Exception) -> str:
    """Человекочитаемый текст доменной/прикладной ошибки движка (2.4, §5.3)."""
    from ..application.errors import ApplicationError
    from ..domain.types.errors import (
        ConfigError,
        IncompletePeriodError,
        IncompleteTimesheetError,
        InvalidInputDataError,
        InvariantViolationError,
        UnknownDayCodeError,
        UnknownTimesheetValueError,
    )
    if isinstance(exc, ConfigError):
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
