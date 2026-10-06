"""Человекочитаемые тексты флагов, исключений и трассы — только здесь (0.1 п.7, 12.13)."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from ..domain.codes_registry import flag_codes as F
from ..domain.codes_registry import reason_codes as R

FLAG_TITLES = {
    F.LATE: "Опоздание", F.EARLY_DEPARTURE: "Ранний уход", F.ABSENCE_GAP: "Отлучился (согласовано)",
    F.MISSED_DAY: "Не пришёл", F.OFF_SHIFT_ATTENDANCE: "Работа вне Графика",
    F.ACTIVITY_REQUIRES_REVIEW: "Отметка в день отсутствия — проверить", F.SESSION_OPEN: "Смена не закрыта",
}
FLAG_SEVERITY = {F.LATE: "warn", F.EARLY_DEPARTURE: "warn", F.ABSENCE_GAP: "muted", F.MISSED_DAY: "danger",
                 F.OFF_SHIFT_ATTENDANCE: "info", F.ACTIVITY_REQUIRES_REVIEW: "warn", F.SESSION_OPEN: "danger"}
REASON_TITLES = {
    R.OPENING_ROUNDED: "Входящий остаток нормализован к новому шагу", R.PLAN_EQUALS_FACT: "Применён «План=Факт»",
    R.UNPAID_CREDITED: "Неоплачиваемая переработка зачислена в банк", R.CODE_PLACED: "Код перенесён в день",
    R.NO_RECEIVER: "Нет дня-приёмника — код отложен на следующий период", R.BANK_APPLIED: "Недостача погашена банком",
    R.CODE_CUT: "Код изъят в погашение недостачи", R.RESIDUAL_CARRIED: "Остаток недостачи перенесён минусом банка",
}


def hm(minutes: int) -> str:
    return "24:00" if minutes >= 1440 else f"{minutes // 60:02d}:{minutes % 60:02d}"


def local_hm(value, tz: str) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value)
    return value.astimezone(ZoneInfo(tz)).strftime("%H:%M")


def hours(minutes: int) -> str:
    h = minutes / 60
    return f"{h:g}"


def flag_text(code: str, data: dict, tz: str) -> str:
    """Текст флага по коду и параметрам."""
    if code == F.LATE:
        actual = data.get("actual_at")
        return (f"Опоздание: ожидался в {local_hm(data.get('expected_at'), tz)}, пришёл в {local_hm(actual, tz)}"
                if actual else f"Ожидался в {local_hm(data.get('expected_at'), tz)}, ещё не пришёл")
    if code == F.EARLY_DEPARTURE:
        return f"Ранний уход: в {local_hm(data.get('actual_at'), tz)} вместо {local_hm(data.get('expected_at'), tz)}"
    if code == F.ABSENCE_GAP:
        return f"Отлучился с {hm(data['gap_start'])}: ожидается в {hm(data['expected_return'])}"
    if code == F.MISSED_DAY:
        segs = ", ".join(f"{hm(a)}–{hm(b)}" for a, b in data.get("shift_segments", ()))
        return f"Не пришёл на смену {segs}"
    if code == F.OFF_SHIFT_ATTENDANCE:
        return f"Пришёл в {local_hm(data.get('first_presence_at'), tz)}, хотя по Графику не ожидался"
    if code == F.ACTIVITY_REQUIRES_REVIEW:
        kind = "приход" if data.get("kind") == "in" else "уход"
        return f"{kind.capitalize()} в {local_hm(data.get('at_utc'), tz)} в день «{data.get('day_code')}» — проверить"
    if code == F.SESSION_OPEN:
        return f"Смена открыта с {local_hm(data.get('open_since'), tz)} — нет отметки «Ушёл»"
    return code


def reason_text(code: str, data: dict) -> str:
    title = REASON_TITLES.get(code, code)
    if code == R.CODE_PLACED:
        return f"{title}: {data['tariff']} {hours(data['minutes'])} ч из {data['source_day']} в {data['placed_day']}"
    if code == R.CODE_CUT:
        return f"{title}: {data['tariff']} {hours(data['taken_minutes'])} ч ({data['source_day']}), " \
               f"погашено {hours(data['paid_minutes'])} ч"
    if code == R.UNPAID_CREDITED:
        return f"{title}: {data['day']} {data['tariff']} {hours(data['taken_minutes'])} ч → " \
               f"{hours(data['credited_minutes'])} ч банка"
    if code == R.BANK_APPLIED:
        return f"{title}: {hours(data['used'])} ч"
    if code == R.NO_RECEIVER:
        return f"{title}: {data['tariff']} {hours(data['minutes'])} ч ({data['source_day']})"
    if code == R.RESIDUAL_CARRIED:
        return f"{title}: {hours(data['residual_minutes'])} ч"
    return title
