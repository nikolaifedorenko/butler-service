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
