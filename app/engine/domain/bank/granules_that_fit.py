def granules_that_fit(rest: int, weight: int, step: int) -> int:
    """Сколько целых гранул по весу помещается в остаток долга."""
    return rest // (step * weight)
