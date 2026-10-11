"""settle() — расчёт часов, кодов УТ, банка, переносов и отчётов (6.4).

Стадии (6.3 — нормативно): 1 валидация входа → 2 нормализация входящих остатков →
3 округление отметок и now → 4 сессии и расчётные интервалы → 5 карточки дней →
6 аккумулятор кодов → 7 credit_unpaid → 8 первичное размещение → 9 доступный банк и
общий долг → (только close) 10 погашение банком, 11 каскад, 12 повторное размещение →
13 переносы и банк → 14 результат. Стадии 6–9 и 13 выполняются и в view; изъятия —
только в close (RUL-VIEW-NO-CUT, INV-VIEW-MODE)."""
from __future__ import annotations

import datetime as dt
from typing import Literal, Sequence

from ..bank.applied_reason import bank_applied_reason
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
from ..day_card.build_day_card import build_day_card
from ..opening.normalize_bank import normalize_opening_bank
from ..opening.normalize_deferred import normalize_deferred
from ..placement.accept_deferred import accept_deferred
from ..placement.canonical_order import sort_deferred
from ..placement.collect_deferred import collect_deferred
from ..placement.created_totals import created_totals
from ..placement.credit_unpaid import credit_unpaid
from ..placement.relocate_codes import relocate_codes
from ..placement.relocate_pending import relocate_pending
from ..placement.seed import seed_codes
from ..presence.presence_intervals import presence_intervals
from ..reports.exceptions import build_exceptions
from ..reports.mgmt_timesheet import build_mgmt_timesheet
from ..reports.trace import StageRecords, build_trace
from ..settings.types import Settings
from ..time.calc_now import calc_now
from ..time.period_days import period_days
from ..time.to_calc_mark import to_calc_mark
from ..types.entities import Adjustment, DeferredBlock, Mark, Period
from ..types.results import SettleResult
from ..validation.validate_inputs import validate_inputs


def settle(period: Period, days: Sequence, marks: Sequence[Mark], opening_mark: Mark | None,
           bank_open: int, adjustments: Sequence[Adjustment], deferred_in: Sequence[DeferredBlock],
           st: Settings, now: dt.datetime, mode: Literal["view", "close"],
           previous_step_minutes: int) -> SettleResult:
    validate_inputs(period, days, adjustments, deferred_in, st, now, mode, previous_step_minutes)
    bank_norm, r_bank_open = normalize_opening_bank(bank_open, previous_step_minutes, st.step_minutes)
    deferred_norm, r_deferred_open = normalize_deferred(sort_deferred(deferred_in, st),
                                                        previous_step_minutes, st.step_minutes)
    calc_marks = tuple(to_calc_mark(m, st) for m in marks)
    calc_opening = to_calc_mark(opening_mark, st) if opening_mark is not None else None
    now_calc = calc_now(now, st)
    intervals = presence_intervals(period, calc_marks, calc_opening, now_calc, st)
    check_sessions(intervals, st.step_minutes)
    by_day = {d.day: d for d in days}
    cards = tuple(build_day_card(by_day[d], intervals.get(d, ()), marks, st)
                  for d in period_days(period))
    check_cards(cards, by_day, st)
    codes = accept_deferred(deferred_norm, seed_codes(cards, by_day, st), st)
    created = created_totals(codes)
    credited = credit_unpaid(cards, codes, st)
    r_place = relocate_codes(cards, by_day, codes, st)
    check_placement(cards, by_day, codes, st)
    adj = sum(a.amount_minutes for a in adjustments)
    avail = available_bank(bank_norm, adj, credited.credited_minutes)
    debt = total_debt(cards, avail)
    used, need, bank_left, sac, r_bank, r_replace = _closing(
        mode, debt, avail, codes, cards, by_day, st)
    out_blocks, r_no_receiver = collect_deferred(codes, st)
    check_deferred(out_blocks, st.step_minutes)
    bank_closed, r_closing = close_bank(bank_left, sac.residual) if mode == "close" else (avail, ())
    result = SettleResult(
        cards=cards, mgmt_timesheet=build_mgmt_timesheet(cards, codes), bank_open_minutes=bank_open,
        bank_open_normalized_minutes=bank_norm, bank_adjustments_minutes=adj,
        bank_closed_minutes=bank_closed, credited_to_bank_minutes=credited.credited_minutes,
        paid_with_bank_minutes=used, total_debt_minutes=debt, residual_debt_minutes=sac.residual,
        cuts=sac.cuts, deferred_blocks=out_blocks, exceptions=build_exceptions(r_no_receiver),
        trace=build_trace(StageRecords(opening=r_bank_open + r_deferred_open,
                                       credit_unpaid=credited.reasons, placement=r_place,
                                       bank=r_bank, cascade=sac.reasons, replacement=r_replace,
                                       closing=r_closing), cards, by_day, st))
    check_result(result, Totals(created, credited.taken_minutes), mode, period)
    return result


def _closing(mode: str, debt: int, avail: int, codes, cards, by_day, st: Settings) -> tuple:
    """Стадии 10–12 (только close): погашение банком → каскад → повторное размещение."""
    if mode != "close":
        return 0, debt, avail, Sacrificed((), (), debt), (), ()
    used, need, bank_left = pay_debt_with_bank(debt, avail)
    r_bank = bank_applied_reason(used, avail, debt)
    sac = sacrifice_codes(need, codes, st)
    check_cascade(need, sac.cuts, sac.residual, st)
    r_replace = relocate_pending(cards, by_day, codes, st)
    check_placement(cards, by_day, codes, st)
    return used, need, bank_left, sac, r_bank, r_replace
