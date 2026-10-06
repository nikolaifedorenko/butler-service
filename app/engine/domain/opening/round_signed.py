def round_signed(value: int, step: int) -> int:
    """До ближайшего кратного шагу; ровно половина — вверх по абсолютной величине (4.6)."""
    sign = -1 if value < 0 else 1
    return sign * ((2 * abs(value) + step) // (2 * step) * step)
