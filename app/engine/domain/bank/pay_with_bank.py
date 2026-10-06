def pay_debt_with_bank(debt: int, positive_bank: int) -> tuple[int, int, int]:
    """Погашение 1:1 → (used, need, bank_left)."""
    used = min(debt, max(0, positive_bank))
    return used, debt - used, max(0, positive_bank) - used
