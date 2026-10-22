"""Построение представлений для HTTP/UI-точек (8.4): вкладка «Управленческий табель»
(16.6), карточки дней с расчётным и информационным планами (v7.1/R39), дни «не в штате»
(7.1, 16.6). Числа — из домена как есть; тексты — formatting."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from app.core.config import settings as app_settings

from ..application.period_view import PeriodView, day_views
from ..domain.types.results import DayView
from .formatting import flag_hint, flag_text, hours, reason_text
from .serialize import plain


def flag_dict(flag, tz) -> dict:
    data = plain(flag.data)
    return {"day": flag.day.isoformat(), "code": flag.code, "title": flag_text(code=flag.code,
            data=dict(flag.data), tz=tz), "hint": flag_hint(flag.code, dict(flag.data), tz),
            "data": data}


def day_view_dict(dv: DayView, tz) -> dict:
    card = dv.card
    return {
        "day": card.day.isoformat(),
        "timesheet_value": card.timesheet_value,
        "plan_minutes": card.plan_minutes,                 # расчётный план = длина окна (R34)
        "plan_hours": hours(card.plan_minutes),
        "timesheet_plan_minutes": dv.timesheet_plan_minutes,  # информационный план строки (R39)
        "timesheet_plan_hours": hours(dv.timesheet_plan_minutes) if dv.timesheet_plan_minutes else "",
        "fact_minutes": card.full_fact_minutes,
        "work_minutes": card.work_minutes,
        "overtime_minutes": card.overtime_minutes,
        "debt_minutes": card.debt_minutes,
        "codes": dict(card.codes),
        "pays_overtime": card.pays_overtime,
        "plan_equals_fact": card.plan_equals_fact_applied,
        "flags": [flag_dict(f, tz) for f in dv.flags],
    }


def _out_of_staff_days(view: PeriodView, requested) -> list[str]:
    """Дни запрошенного периода вне интервала трудоустройства — «не в штате» (16.6)."""
    emp = view.employment
    out = []
    day = requested.start
    while day <= requested.end:
        if day < emp.start or (emp.end is not None and day > emp.end):
            out.append(day.isoformat())
        day += dt.timedelta(days=1)
    return out


def period_view_dict(view: PeriodView, requested, tz=None, detail: bool = False) -> dict:
    tz = tz or app_settings.app_tz      # пояс объекта, а не константа (HARD-02)
    s = view.settle
    return {
        "effective_period": {"start": s.cards[0].day.isoformat() if s.cards else None,
                             "end": s.cards[-1].day.isoformat() if s.cards else None},
        "employment": {"start": view.employment.start.isoformat(),
                       "end": view.employment.end.isoformat() if view.employment.end else None},
        "out_of_staff_days": _out_of_staff_days(view, requested),
        "days": [day_view_dict(dv, tz) for dv in day_views(view)],
        "ut": {day.isoformat(): dict(row) for day, row in s.mgmt_timesheet.items()},
        "bank": {"open": s.bank_open_minutes, "open_normalized": s.bank_open_normalized_minutes,
                 "adjustments": s.bank_adjustments_minutes, "credited": s.credited_to_bank_minutes,
                 "paid": s.paid_with_bank_minutes, "closed": s.bank_closed_minutes,
                 "open_h": hours(s.bank_open_minutes), "closed_h": hours(s.bank_closed_minutes),
                 "adjustments_h": hours(s.bank_adjustments_minutes),
                 "credited_h": hours(s.credited_to_bank_minutes)},
        "debt": {"total": s.total_debt_minutes, "residual": s.residual_debt_minutes,
                 "total_h": hours(s.total_debt_minutes), "residual_h": hours(s.residual_debt_minutes)},
        "deferred": [{"source_day": b.source_day.isoformat(), "tariff": b.tariff,
                      "minutes": b.minutes, "hours": hours(b.minutes)}
                     for b in s.deferred_blocks],
        "exceptions": [{"code": r.code, "text": reason_text(r.code, plain(r.data))}
                       for r in s.exceptions],
        "cuts": [{"source_day": c.source_day.isoformat(),
                  "placed_day": c.placed_day.isoformat() if c.placed_day else None,
                  "tariff": c.tariff, "taken_minutes": c.taken_minutes,
                  "paid_minutes": c.paid_minutes} for c in s.cuts],
        "totals": _totals(s),
        "trace": [{"step": r.step, "code": r.code,
                   "text": reason_text(r.code, plain(r.data))} for r in s.trace] if detail else [],
    }


def _totals(s) -> dict:
    totals: dict[str, int] = {}
    for row in s.mgmt_timesheet.values():
        for tariff, minutes in row.items():
            totals[tariff] = totals.get(tariff, 0) + minutes
    return totals


def session_view_dict(sv, tz) -> dict:
    sess = sv.session
    local = lambda m: m.astimezone(ZoneInfo(str(tz)))  # noqa: E731
    return {
        "employee_id": sv.employee_id,
        "start_utc": sess.start.isoformat(),
        "end_utc": sess.end.isoformat() if sess.end else None,
        "open": sess.end is None,
        "started_before_range": sv.started_before_range,
        "closed_after_range": sv.closed_after_range,
        "start_local": local(sess.start).isoformat(),
        "end_local": local(sess.end).isoformat() if sess.end else None,
        "minutes": int((sess.end - sess.start).total_seconds() // 60) if sess.end else None,
    }


def board_dict(board, tz) -> dict:
    # Моменты домена — UTC; человекочитаемые HH:MM — только в часовом поясе
    # объекта (дефект 16.10.2026: shift_today отдавался сырыми UTC-моментами,
    # фронт резал из них HH:MM и карточка показывала окно со сдвигом пояса).
    local = lambda m: m.astimezone(ZoneInfo(str(tz)))  # noqa: E731
    return {
        "at_work_now": board.at_work_now,
        "expected_now": board.expected_now,
        "open_session_cards": [{"employee_id": c.employee_id,
                                "open_since": c.open_since_utc.isoformat(),
                                "open_since_hm": c.open_since_utc.astimezone(ZoneInfo(str(tz))).strftime("%H:%M"),
                                "minutes_open": c.minutes_open,
                                "hours_open": hours(c.minutes_open),
                                "expected_today": c.expected_today,
                                "shift_today": [[s.isoformat(), e.isoformat()]
                                                for s, e in c.shift_today],
                                "shift_today_hm": [[local(s).strftime("%H:%M"),
                                                    local(e).strftime("%H:%M")]
                                                   for s, e in c.shift_today]}
                               for c in board.open_session_cards],
        "yet_to_come": [{"employee_id": a.employee_id,
                         "expected_at": a.expected_at_utc.isoformat(),
                         "expected_at_hm": a.expected_at_utc.astimezone(ZoneInfo(str(tz))).strftime("%H:%M"),
                         "already_started": a.already_started}
                        for a in board.yet_to_come],
    }
