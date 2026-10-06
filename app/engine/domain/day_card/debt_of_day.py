def debt_of_day(plan: int, work: int) -> int:
    """Р9: недостача = max(0, план − рабочее время). «Сальдо» нет."""
    return max(0, plan - work)
