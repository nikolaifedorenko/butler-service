"""settle() — расчёт часов, кодов УТ, банка и каскада (6.4). Каждая строка — вызов стадии."""
from __future__ import annotations

import datetime as dt
from typing import Sequence

from ..bank.available_bank import available_bank
from ..bank.close_bank import close_bank
from ..bank.pay_with_bank import pay_debt_with_bank
from ..bank.sacrifice import Sacrificed, sacrifice_codes
from ..bank.total_debt import total_debt
from ..checks.check_cards import check_cards
from ..checks.check_cascade import check_cascade
from ..checks.check_deferred import check_deferred
from ..checks.check_placement import check_placement
from ..checks.check_result import Totals, check_result
from ..checks.check_sessions import check_sessions
from ..codes_registry.reason_codes import BANK_APPLIED
from ..opening.normalize_bank import normalize_opening_bank
from ..opening.normalize_deferred import normalize_deferred
from ..placement.accept_deferred import accept_deferred
from ..placement.collect_deferred import collect_deferred
from ..placement.created_totals import created_totals
from ..placement.credit_unpaid import credit_unpaid
from ..placement.relocate_codes import relocate_codes
from ..placement.relocate_pending import relocate_pending
from ..placement.seed import seed_codes
from ..presence.open_session_since import open_session_since
from ..presence.presence_intervals import presence_intervals
from ..presence.sort_marks import sort_marks
from ..reports.exceptions import build_exceptions
from ..reports.mgmt_timesheet import build_mgmt_timesheet
from ..reports.trace import build_trace
from ..settings.types import Settings
from ..time.calc_now import calc_now
from ..time.to_calc_mark import to_calc_mark
from ..time.today_of import today_of
from ..types.entities import Adjustment, DeferredBlock, Mark, Period
from ..types.results import Reason, SettleResult
from .build_cards import build_cards
from .check_aware import check_aware
from .check_close_allowed import check_close_allowed
from .check_known_day_codes import check_known_day_codes
from .pef_reasons import pef_reasons


def _period_days(period: Period) -> list[dt.date]:
    return [period.start + dt.timedelta(days=i) for i in range((period.end - period.start).days + 1)]


def _bank_reason(used: int, bank: int, debt: int) -> tuple[Reason, ...]:
    data = {"before": bank, "used": used, "after": bank - used, "debt_before": debt, "debt_after": debt - used}
    return (Reason("bank", BANK_APPLIED, data),) if used > 0 else ()


def settle(period: Period, days: Sequence, marks: Sequence[Mark], opening_mark: Mark | None,
           bank_open: int, adjustments: Sequence[Adjustment], deferred_in: Sequence[DeferredBlock],
           st: Settings, now: dt.datetime, mode: str, previous_step_minutes: int) -> SettleResult:
    # 1. валидация входа
    check_aware(now)
    check_known_day_codes(days, st)
    check_close_allowed(period, now, mode, st.tz)
    # 2. нормализация входящих остатков
    bank_norm, r_bank = normalize_opening_bank(bank_open, previous_step_minutes, st.step_minutes)
    deferred, r_def = normalize_deferred(deferred_in, previous_step_minutes, st.step_minutes)
    # 3. округление отметок и now
    calc = sort_marks([to_calc_mark(m, st) for m in ([opening_mark] if opening_mark else []) + list(marks)])
    today = today_of(now, st.tz)
    # 4. присутствие
    presence = presence_intervals(_period_days(period), calc, calc_now(now, st), today, st.tz)
    check_sessions(presence.intervals, st.step_minutes)
    # 5. карточки дней
    by_day = {d.day: d for d in days}
    cards = build_cards(days, presence, calc, st)
    check_cards(cards, st.step_minutes)
    # 6. аккумулятор кодов
    codes = accept_deferred(deferred, seed_codes(cards, by_day, st))
    created = created_totals(codes)
    # 7. неоплачиваемая переработка → банк по весу
    credited = credit_unpaid(cards, codes, st)
    # 8. первичное размещение
    r_place = relocate_codes(cards, by_day, codes, st)
    check_placement(cards, by_day, codes, st)
    # 9. доступный банк и общий долг
    adj = sum(a.amount_minutes for a in adjustments)
    avail = available_bank(bank_norm, adj, credited.credited_minutes)
    debt = total_debt(cards, avail)
    # 10–13. close: банк, каскад, повторное размещение, закрывающий банк
    used, need, bank_left = pay_debt_with_bank(debt, avail) if mode == "close" else (0, debt, avail)
    sac = sacrifice_codes(need, codes, st) if mode == "close" else Sacrificed((), (), debt)
    if mode == "close":
        check_cascade(need, sac.cuts, sac.residual, st)
    r_replace = relocate_pending(cards, by_day, codes, st) if mode == "close" else ()
    check_placement(cards, by_day, codes, st)
    out_blocks, r_noreceiver = collect_deferred(codes, st)
    check_deferred(out_blocks, st.step_minutes)
    bank_closed, r_closing = close_bank(bank_left, sac.residual) if mode == "close" else (avail, ())
    # 14. результат
    result = SettleResult(
        cards=cards, mgmt_timesheet=build_mgmt_timesheet(cards, codes), bank_open_minutes=bank_open,
        bank_open_normalized_minutes=bank_norm, bank_adjustments_minutes=adj, bank_closed_minutes=bank_closed,
        credited_to_bank_minutes=credited.credited_minutes, paid_with_bank_minutes=used,
        total_debt_minutes=debt, residual_debt_minutes=sac.residual, cuts=sac.cuts,
        deferred_blocks=out_blocks,
        open_session_since_utc=open_session_since(calc, min(period.end, today)),
        exceptions=build_exceptions(r_noreceiver),
        trace=build_trace(r_bank, r_def, pef_reasons(cards, by_day, st), credited.reasons, r_place,
                          _bank_reason(used, max(0, avail), debt), sac.reasons, r_replace, r_closing))
    check_result(result, Totals(created, credited.taken_minutes), mode)
    return result
