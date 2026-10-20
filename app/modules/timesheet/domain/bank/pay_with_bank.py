"""pay_debt_with_bank(debt, available) — стадия 10 (только close): банк гасит долг 1:1
до изъятия кодов. Возвращает (used, need, bank_left); никакого каскада внутри (6.5 п.1)."""
from __future__ import annotations


def pay_debt_with_bank(debt: int, available_bank: int) -> tuple[int, int, int]:
    positive = max(0, available_bank)
    used = min(debt, positive)
    return used, debt - used, positive - used
