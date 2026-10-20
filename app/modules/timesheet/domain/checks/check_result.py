"""Итоговые инварианты (10.1: после стадии 14, по режиму): INV-TOTAL-DEBT,
INV-BANK-CLOSED, INV-CLOSE-BALANCE, INV-VIEW-MODE, INV-MINUTES-CONSERVED,
INV-CARDS-COVER-PERIOD."""
from __future__ import annotations

from dataclasses import dataclass

from ..codes_registry.invariant_codes import (
    INV_BANK_CLOSED,
    INV_CARDS_COVER_PERIOD,
    INV_CLOSE_BALANCE,
    INV_MINUTES_CONSERVED,
    INV_TOTAL_DEBT,
    INV_VIEW_MODE,
)
from ..time.period_days import period_days
from ..types.entities import Period
from ..types.results import SettleResult
from ._fail import fail


@dataclass(frozen=True)
class Totals:
    """Контрольные суммы стадий 6–7 для INV-MINUTES-CONSERVED (физические минуты)."""

    created: int          # собственные + нормализованные входящие (до снятия неоплачиваемых)
    unpaid_taken: int     # снятые неоплачиваемые — физические, не взвешенные


def _available(result: SettleResult) -> int:
    return (result.bank_open_normalized_minutes + result.bank_adjustments_minutes
            + result.credited_to_bank_minutes)


def _check_debt(result: SettleResult, available: int) -> None:
    expected = sum(c.debt_minutes for c in result.cards) + max(0, -available)
    if result.total_debt_minutes != expected:
        fail(INV_TOTAL_DEBT, {"total": result.total_debt_minutes, "expected": expected})


def _check_closed(result: SettleResult, available: int) -> None:
    expected = max(0, available) - result.paid_with_bank_minutes - result.residual_debt_minutes
    if result.bank_closed_minutes != expected:
        fail(INV_BANK_CLOSED, {"closed": result.bank_closed_minutes, "expected": expected})
    paid_cuts = sum(c.paid_minutes for c in result.cuts)
    total = result.total_debt_minutes
    positive = max(0, available)
    if total != result.paid_with_bank_minutes + paid_cuts + result.residual_debt_minutes \
            or result.residual_debt_minutes < 0 \
            or not 0 <= result.paid_with_bank_minutes <= min(total, positive):
        fail(INV_CLOSE_BALANCE, {"total": total, "paid_bank": result.paid_with_bank_minutes,
                                 "paid_cuts": paid_cuts, "residual": result.residual_debt_minutes})


def _check_view(result: SettleResult, available: int) -> None:
    if result.paid_with_bank_minutes != 0 or result.cuts \
            or result.residual_debt_minutes != result.total_debt_minutes \
            or result.bank_closed_minutes != available:
        fail(INV_VIEW_MODE, {"paid": result.paid_with_bank_minutes, "cuts": len(result.cuts),
                             "residual": result.residual_debt_minutes,
                             "bank_closed": result.bank_closed_minutes})


def _check_conserved(result: SettleResult, totals: Totals) -> None:
    placed = sum(m for row in result.mgmt_timesheet.values() for m in row.values())
    outgoing = sum(b.minutes for b in result.deferred_blocks)
    cut = sum(c.taken_minutes for c in result.cuts)
    if totals.created != placed + outgoing + totals.unpaid_taken + cut:
        fail(INV_MINUTES_CONSERVED, {"created": totals.created, "placed": placed,
                                     "outgoing": outgoing, "unpaid_taken": totals.unpaid_taken,
                                     "cut": cut})


def _check_cover(result: SettleResult, period: Period) -> None:
    expected = period_days(period)
    if tuple(c.day for c in result.cards) != expected:
        fail(INV_CARDS_COVER_PERIOD, {"cards": len(result.cards), "period_days": len(expected)})


def check_result(result: SettleResult, totals: Totals, mode: str, period: Period) -> None:
    available = _available(result)
    _check_debt(result, available)
    _check_closed(result, available) if mode == "close" else _check_view(result, available)
    _check_conserved(result, totals)
    _check_cover(result, period)
