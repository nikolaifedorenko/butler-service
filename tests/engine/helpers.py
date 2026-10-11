"""Помощники приёмочных тестов (11, 13 п.1): компактная запись Табеля, отметок,
Графика и настроек; полное сравнение SettleResult/FlagsResult в канонической форме (3.4).

Единицы таблиц примеров — часы (дробные через запятую); внутреннее представление —
целые минуты. «24:00» — 00:00 следующих календарных суток.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from zoneinfo import ZoneInfo

from app.engine.domain.flags.evaluate_flags import evaluate_flags
from app.engine.domain.pipeline.settle import settle
from app.engine.domain.settings.defaults import default_settings
from app.engine.domain.settings.types import (
    MOD_COUNTS_IN_UT,
    MOD_DOUBLE,
    MOD_PAYS,
    MOD_PLAN_EQUALS_FACT,
    PEF_AUTO,
    PEF_NO,
    PEF_YES,
    ModifierEntry,
    Settings,
)
from app.engine.domain.types.entities import (
    Absence,
    Adjustment,
    Day,
    DeferredBlock,
    Mark,
    Period,
    Shift,
)

TZ = ZoneInfo("Europe/Moscow")
UTC = dt.timezone.utc
Y = 2026
EMP = "e1"
H = 60


# ── даты и моменты ────────────────────────────────────────────────────────────

def d(n: int, month: int = 10) -> dt.date:
    return dt.date(Y, month, n)


def at(n: int, hh: int, mm: int = 0, ss: int = 0, month: int = 10) -> dt.datetime:
    """Локальный момент → UTC-aware. hh = 24 — 00:00 следующих суток."""
    local = dt.datetime(Y, month, n, 0, 0, tzinfo=TZ) + dt.timedelta(hours=hh, minutes=mm, seconds=ss)
    return local.astimezone(UTC)


def period(first: dt.date, last: dt.date) -> Period:
    return Period(first, last)


def midnight_after(date: dt.date) -> dt.datetime:
    """00:00 дня после date (местное) — типовой now для close (преамбула 11)."""
    nxt = date + dt.timedelta(days=1)
    return dt.datetime.combine(nxt, dt.time(0), TZ).astimezone(UTC)


# ── Табель ────────────────────────────────────────────────────────────────────

def day(n: int, value: str, month: int = 10, group: str = "Смена 1", emp: str = EMP) -> Day:
    code, _, hours = value.partition(" ")
    minutes = int(round(float(hours.replace(",", ".")) * H)) if hours else 0
    return Day(d(n, month), code, minutes, emp, group)


def day_on(date: dt.date, value: str, group: str = "Смена 1", emp: str = EMP) -> Day:
    code, _, hours = value.partition(" ")
    minutes = int(round(float(hours.replace(",", ".")) * H)) if hours else 0
    return Day(date, code, minutes, emp, group)


# ── отметки ───────────────────────────────────────────────────────────────────

def IN(n: int, hh: int, mm: int = 0, ss: int = 0, month: int = 10, emp: str = EMP) -> Mark:
    return Mark(emp, at(n, hh, mm, ss, month), "in")


def OUT(n: int, hh: int, mm: int = 0, ss: int = 0, month: int = 10, emp: str = EMP) -> Mark:
    return Mark(emp, at(n, hh, mm, ss, month), "out")


def mark_at(moment: dt.datetime, kind: str, emp: str = EMP) -> Mark:
    return Mark(emp, moment, kind)


# ── модификаторы и настройки ──────────────────────────────────────────────────

def mod(name: str, value, n: int | None = None, month: int = 10, employee: str | None = None,
        group: str | None = None, period_: Period | None = None) -> ModifierEntry:
    return ModifierEntry(name, value, employee_id=employee, group=group,
                         day=d(n, month) if n is not None else None, period=period_)


def double(n: int | None = None, month: int = 10, group: str | None = None,
           period_: Period | None = None, employee: str | None = None) -> ModifierEntry:
    return mod(MOD_DOUBLE, True, n, month, employee, group, period_)


def unpaid(n: int | None = None, month: int = 10) -> ModifierEntry:
    return mod(MOD_PAYS, False, n, month)


def not_in_ut(n: int | None = None, month: int = 10) -> ModifierEntry:
    return mod(MOD_COUNTS_IN_UT, False, n, month)


def pef(value: str, n: int | None = None, month: int = 10, group: str | None = None,
        period_: Period | None = None, employee: str | None = None) -> ModifierEntry:
    return mod(MOD_PLAN_EQUALS_FACT, value, n, month, employee, group, period_)


PEF_YES_, PEF_NO_, PEF_AUTO_ = PEF_YES, PEF_NO, PEF_AUTO


def settings(modifiers=(), **overrides) -> Settings:
    return dataclasses.replace(default_settings(), modifiers=tuple(modifiers), **overrides)


# ── График (смены и отсутствия) ───────────────────────────────────────────────

def shift(start: dt.datetime, end: dt.datetime, emp: str = EMP) -> Shift:
    return Shift(emp, start, end)


def absence(start: dt.datetime, end: dt.datetime, emp: str = EMP) -> Absence:
    return Absence(emp, start, end)


def shifts_from_days(rows, st: Settings | None = None) -> tuple[Shift, ...]:
    """График, построенный из Табеля по окнам CFG-WINDOWS (преамбула 11, 16.3):
    значение с часами → смена = окно целиком; у кодов без часов смены нет."""
    st = st or default_settings()
    out = []
    for row in rows:
        from app.engine.domain.day_card.window_of_day import window_of_day
        w = window_of_day(row, st)
        if w is None:
            continue
        start = dt.datetime.combine(row.day, dt.time(0), TZ) + dt.timedelta(minutes=w.start_minute)
        end = dt.datetime.combine(row.day, dt.time(0), TZ) + dt.timedelta(minutes=w.end_minute)
        out.append(Shift(row.employee_id, start.astimezone(UTC), end.astimezone(UTC)))
    return tuple(out)


# ── запуск расчётов ───────────────────────────────────────────────────────────

def run_settle(prd: Period, rows, marks, opening: Mark | None = None, bank: int = 0,
               adjustments=(), deferred=(), st: Settings | None = None, now=None,
               mode: str = "close", prev_step: int = 60):
    st = st or default_settings()
    now = now if now is not None else midnight_after(prd.end)
    return settle(prd, list(rows), list(marks), opening, bank, list(adjustments),
                  list(deferred), st, now, mode, prev_step)


def run_flags(prd: Period, rows, result, marks, opening: Mark | None = None,
              shifts=(), absences=(), st: Settings | None = None, now=None):
    st = st or default_settings()
    now = now if now is not None else midnight_after(prd.end)
    pef_map = {c.day: c.plan_equals_fact_applied for c in result.cards}
    return evaluate_flags(prd, list(rows), pef_map, list(marks), opening, list(shifts),
                          list(absences), st, now)


def run(prd: Period, rows, marks, opening: Mark | None = None, bank: int = 0,
        adjustments=(), deferred=(), st: Settings | None = None, now=None,
        mode: str = "close", prev_step: int = 60, shifts=None, absences=(),
        with_flags: bool = False):
    """settle (+ evaluate_flags, если with_flags либо заданы shifts/absences)."""
    st = st or default_settings()
    result = run_settle(prd, rows, marks, opening, bank, adjustments, deferred, st, now,
                        mode, prev_step)
    if with_flags or shifts is not None or absences:
        flags = run_flags(prd, rows, result, marks, opening,
                          shifts_from_days(rows, st) if shifts is None else shifts,
                          absences, st, now)
        return result, flags
    return result, None


# ── сравнение результата (каноническая форма, 3.4) ───────────────────────────

def _minutes(hours) -> int:
    if isinstance(hours, str):
        hours = float(hours.replace(",", "."))
    return int(round(hours * H))


def parse_codes(text: str) -> dict[str, int]:
    """«ДЯ2 2, ДН 1» → {"ДЯ2": 120, "ДН": 60}; «—»/«» → {}."""
    text = (text or "").strip()
    if text in ("", "—", "-"):
        return {}
    out: dict[str, int] = {}
    for part in text.split(","):
        code, _, hours = part.strip().partition(" ")
        out[code] = out.get(code, 0) + _minutes(hours)
    return out


def card_tuple(card) -> tuple:
    return (card.day, card.plan_minutes, card.work_minutes, card.debt_minutes,
            dict(card.codes), card.full_fact_minutes, card.overtime_minutes,
            card.timesheet_value, card.pays_overtime, card.plan_equals_fact_applied)


def assert_cards(result, expected: list[tuple]) -> None:
    """expected: (день, план ч, рабочее ч, недостача ч, коды-текст|словарь) — как в таблице
    примера; полное сравнение карточек в каноническом порядке (по возрастанию дня)."""
    assert len(result.cards) == len(expected), f"карточек {len(result.cards)}, ожидалось {len(expected)}"
    days = [c.day for c in result.cards]
    assert days == sorted(days), "карточки не по возрастанию дня"
    for card, exp in zip(result.cards, expected, strict=True):
        e_day, plan, work, debt = exp[0], exp[1], exp[2], exp[3]
        codes = exp[4] if len(exp) > 4 else None
        assert card.day == e_day, f"день {card.day} != {e_day}"
        assert card.plan_minutes == _minutes(plan), f"{e_day}: план {card.plan_minutes} != {_minutes(plan)}"
        assert card.work_minutes == _minutes(work), f"{e_day}: рабочее {card.work_minutes} != {_minutes(work)}"
        assert card.debt_minutes == _minutes(debt), f"{e_day}: недостача {card.debt_minutes} != {_minutes(debt)}"
        if codes is not None:
            codes_map = parse_codes(codes) if isinstance(codes, str) else dict(codes)
            assert dict(card.codes) == codes_map, f"{e_day}: коды {dict(card.codes)} != {codes_map}"
        assert card.full_fact_minutes == card.work_minutes + card.overtime_minutes


def assert_mgmt(result, expected: dict) -> None:
    """expected: {день: «ДЯ 2, ДН 2»}; ключ на каждый день периода (3.4)."""
    got = {day: dict(row) for day, row in result.mgmt_timesheet.items()}
    want = {day: parse_codes(text) for day, text in expected.items()}
    assert set(got) == set(want), f"дни УТ {sorted(set(got) ^ set(want))}"
    for day, row in want.items():
        assert got[day] == row, f"УТ {day}: {got[day]} != {row}"


def assert_bank(result, closed: float | None = None, open_: float | None = None,
                normalized: float | None = None, adjustments: float | None = None,
                credited: float | None = None, paid: float | None = None,
                total_debt: float | None = None, residual: float | None = None) -> None:
    checks = (("bank_closed_minutes", closed), ("bank_open_minutes", open_),
              ("bank_open_normalized_minutes", normalized), ("bank_adjustments_minutes", adjustments),
              ("credited_to_bank_minutes", credited), ("paid_with_bank_minutes", paid),
              ("total_debt_minutes", total_debt), ("residual_debt_minutes", residual))
    for field, hours in checks:
        if hours is not None:
            got = getattr(result, field)
            want = hours * H if isinstance(hours, (int, float)) else _minutes(hours)
            assert got == want, f"{field}: {got} != {want}"


def assert_deferred(result, expected) -> None:
    """expected: [(день-источник, тариф, минуты)] в каноническом порядке (3.4)."""
    got = [(b.source_day, b.tariff, b.minutes) for b in result.deferred_blocks]
    assert got == list(expected), f"deferred {got} != {list(expected)}"


def assert_cuts(result, expected) -> None:
    """expected: [(source_day, placed_day|None, тариф, снято мин, погашено мин)] в порядке каскада."""
    got = [(c.source_day, c.placed_day, c.tariff, c.taken_minutes, c.paid_minutes)
           for c in result.cuts]
    assert got == list(expected), f"cuts {got} != {list(expected)}"


def assert_exceptions(result, expected_codes) -> None:
    got = [r.code for r in result.exceptions]
    assert got == list(expected_codes), f"exceptions {got} != {list(expected_codes)}"


def assert_trace_codes(result, expected) -> None:
    got = [(r.step, r.code) for r in result.trace]
    assert got == list(expected), f"trace {got} != {list(expected)}"


def _flag_tuple(flag) -> tuple:
    exp_at = flag.data.get("expected_at")
    act_at = flag.data.get("actual_at")
    first = flag.data.get("first_presence_at")
    return (flag.day, flag.code, exp_at, act_at, first)


def _moment(value):
    return at(*value) if isinstance(value, tuple) else value


def assert_flags(flags_result, expected) -> None:
    """expected: [(день, код, expected_at=(n,hh,mm[,ss])|None, actual_at=…|None
    [, first_presence_at=…|«*»])] — моменты локальные; «*» — любой (проверяется отдельно);
    порядок флагов — канонический (3.4)."""
    got = [_flag_tuple(f) for f in flags_result.flags]
    want = []
    for exp in expected:
        day_, code, exp_at, act_at = exp[0], exp[1], exp[2], exp[3]
        first = exp[4] if len(exp) > 4 else "*"
        want.append((day_, code, _moment(exp_at), _moment(act_at), first))
    assert len(got) == len(want), f"флаги:\n  есть {got}\n  надо {want}"
    for g, w in zip(got, want, strict=True):
        for gv, wv in zip(g, w, strict=True):
            if wv == "*":
                continue
            assert gv == wv, f"флаги:\n  есть {got}\n  надо {want}"


def assert_no_flags(flags_result) -> None:
    got = [_flag_tuple(f) for f in flags_result.flags]
    assert got == [], f"ожидались отсутствие флагов, есть {got}"


def deferred(source: dt.date, tariff: str, minutes: int) -> DeferredBlock:
    return DeferredBlock(source, tariff, minutes)


def adjustment(amount: int, prd: Period, reason: str = "MANUAL", note: str | None = None) -> Adjustment:
    return Adjustment(amount, prd, reason, note)
