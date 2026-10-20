"""Запись BANK_APPLIED (6.2): формируется при used > 0; before/after — положительный банк."""
from __future__ import annotations

from ..codes_registry.reason_codes import BANK_APPLIED, STEP_BANK
from ..types.results import Reason


def bank_applied_reason(used: int, available_bank: int, debt: int) -> tuple[Reason, ...]:
    if used <= 0:
        return ()
    positive = max(0, available_bank)
    return (Reason(STEP_BANK, BANK_APPLIED, {
        "before": positive, "used": used, "after": positive - used,
        "debt_before": debt, "debt_after": debt - used}),)
