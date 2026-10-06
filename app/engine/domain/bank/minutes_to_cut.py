from .granules_that_fit import granules_that_fit


def minutes_to_cut(rest: int, weight: int, available: int, step: int) -> int:
    """Т6.1: min(available // q, rest // (q·weight)) · q."""
    return min(available // step, granules_that_fit(rest, weight, step)) * step
